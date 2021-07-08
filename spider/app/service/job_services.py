from typing import List, Any, Callable, Union, TypeVar, Optional
from .base_services import BaseJobService
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.job import Job as APJob
from ..models.db_models import Job, Specification
from ..models.data_models import JobData, Schedule, JobStatus
from ..enums import JobState
from datetime import datetime
from asyncio import Lock
from ..exceptions import ResourceNotFound

import logging
from logging import Logger, getLogger

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(funcName)s |%(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S%z")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

TZInfo = TypeVar("TZInfo")
Datetime = TypeVar("Datetime")
SpecificationClass = TypeVar("SpecificationClass")

class AsyncJobService(BaseJobService):
    """ Provides async job management using APScheduler

    """
    def __init__(self,
                 async_scheduler: BaseScheduler,
                 job_model: Job = Job,
                 job_data_model: JobData = JobData,
                 specification_model: SpecificationClass = Specification,
                 datetime: Datetime = datetime,
                 lock: Lock = Lock,
                 logger: Logger = getLogger(f"{__name__}.AsyncJobService")) -> None:
        self._async_scheduler = async_scheduler
        self._job_model = job_model
        self._job_data_model = job_data_model
        self._specification_model = specification_model
        self._datetime = datetime
        self._lock = lock() # is lock necessary?
        self._logger = logger

    async def add_job(self, func: Callable, schedule: Schedule, specification_id: str = None,
                      trigger: BaseTrigger = None, name: str = None,
                      description: str = "", misfire_grace_time: int = None,
                      coalesce: bool = False, max_instances: int = 1,
                      next_run_time:str = None, jobstore: str = 'default',
                      executor: str = 'default', replace_existing: bool = False,
                      **trigger_args) -> JobData:
        """ Create a new job

        Args:
            func
            name
            description
            trigger
            
        """
        
        # might be blocking under the hood...
        # TODO: run in a separate thread to avoid blocking the event loop
        try:
            self._logger.info("Creating a new job")
            job_name = f"{func.__name__}" if name is None else name
            
            job = Job(
                name=job_name,
                description=description,
                schedule=schedule,
                current_state=JobState.WORKING,
                spec_id=specification_id
            )
            ap_job = self._async_scheduler.add_job(
                func=func, trigger=trigger, id=str(job.job_id), name=name,
                **(schedule.dict())
            )
            job_next_run = ap_job.next_run_time if next_run_time is None else next_run_time
            job.next_run_time = job_next_run
            self._logger.info("Saving to db...")
            await job.save()
            self._logger.info("Done!")
            return self._job_data_model.from_db_model(job)
        except Exception as e:
            self._logger.error(f"{e}")
            raise e

    async def update_job(self,
                         job_id: str,
                         func: Callable = None,
                         specification_id: str = None,
                         schedule: Schedule = None,
                         status: JobStatus = None,
                         **changes) -> None:
        if type(job_id) is not str:
            job_id = str(job_id)
            
        if func is not None:
            changes['func'] = func
        
        if specification_id is not None:
            changes['spec_id'] = specification_id
            
        if schedule is not None:
            changes['schedule'] = schedule
            
        if status is not None:
            changes['current_state'] = status
        
        try:
            ap_job = self._async_scheduler.get_job(job_id)
            
            if ap_job is None:
                resource_not_found_error = ResourceNotFound(
                    f"Job with id {job_id} does not exist.")
                self._logger.error(f"{resource_not_found_error}")
                raise resource_not_found_error
            
            if schedule is not None:
                # apscheduler uses a different api to reschedule a job
                ap_job.reschedule(trigger='cron', **schedule.dict())
                
            if status is not None:
                if status.value == 'paused':
                    # apscheduler uses a different api to reschedule a job
                    ap_job.pause()
                elif status.value == 'resumed':
                    ap_job.resume()
            
            ap_update = {key: changes[key]
                         for key in changes if hasattr(ap_job, key)}
            if len(ap_update):
                ap_job.modify(**ap_update)
            
            updates = {key: changes[key] for key in changes if key in self._job_model.__fields__}
            await self._job_model.update_one(
                filter={"job_id": job_id}, update=updates)
        except AttributeError:
            self._logger.error(f"Job with id {job_id} is not found.")
            raise IndexError("Job is not found")
        except Exception as e:
            self._logger.error(f"{e}")
            raise e
        
    async def apply_specification(self, job_id: str, specification_id: str) -> None:
        if type(specification_id) is not str:
            specification_id = str(specification_id)
            
        if type(job_id) is not str:
            job_id = str(job_id)
            
        try:
            specification = await self._specification_model.get_one(
                {"specification_id": specification_id})
            
            if specification is None:
                resource_not_found_error = ResourceNotFound(
                    f"Specification with id {specification_id} does not exist.")
                self._logger.error(f"{resource_not_found_error}")
                raise resource_not_found_error
            
            await self._job_model.update_one(
                filter={"job_id": job_id}, update={"spec_id": specification_id})
        except Exception as e:
            self._logger.error(f"{e}")
            raise e
        
    async def _update_next_run_time(self, job_id: str, 
                                    write_back_to_db: bool = False) -> Job:
        """ Update job's next run time from apscheduler's job
        """
        ap_job = self._async_scheduler.get_job(job_id)
        job = await self._job_model.get_one({'job_id': job_id})
        job.next_run_time = ap_job.next_run_time

        if write_back_to_db:
            await job.update({"next_run_time": ap_job.next_run_time})
        
        return job

    async def reschedule_job(self, job_id: str, trigger: str = 'cron', 
                             year: Union[int, str] = None, month: Union[int, str] = None,
                             day: Union[int, str] = None, week: Union[int, str] = None,
                             day_of_week: Union[int, str] = None, hour: Union[int, str] = None,
                             minute: Union[int, str] = None, second: Union[int, str] = None,
                             start_date: Union[datetime, str] = None,
                             end_date: Union[datetime, str] = None,
                             timezone: Union[TZInfo, str] = None, **kwargs) -> JobData:
        if type(job_id) is not str:
            job_id = str(job_id)

        self._logger.info(f"Reschedule job {job_id}")
        try:
            if trigger != 'cron':
                self._async_scheduler.reschedule_job(job_id=job_id, trigger=trigger, **kwargs)
            else:
                self._async_scheduler.reschedule_job(
                    job_id=job_id, trigger='cron', year=year, month=month, day=day,
                    week=week, day_of_week=day_of_week, hour=hour, minute=minute,
                    second=second, start_date=start_date, end_date=end_date, timezone=timezone)
            job = await self._update_next_run_time(job_id)
            self._logger.info(f"Done!")
            return self._job_data_model.from_db_model(job)
        except Exception as e:
            self._logger.error(f"{e}")
            raise e
 
    async def delete_job(self, job_id: str) -> None:
        if type(job_id) is not str:
            job_id = str(job_id)

        self._logger.info(f"Delete job {job_id}")
        try:
            self._async_scheduler.remove_job(job_id)
            await self._job_model.delete_one({"job_id": job_id})

            self._logger.info(f"Done!")
        except Exception as e:
            self._logger.error(f"{e}")
            raise e

    async def delete_jobs(self, job_ids: List[str]) -> None:
        self._logger.info(f"Delete jobs {job_ids}")
        try:
            job_id_set = set(job_ids)
            ap_jobs_to_remove = []
            for job in self._async_scheduler.get_jobs():
                if job.id in job_id_set:
                    job.remove()
                    ap_jobs_to_remove.append(job)
            query = {"job_id": {"$in": [str(job.id) for job in ap_jobs_to_remove]}}
            await self._job_model.delete_many(query)

            self._logger.info(f"Done!")
        except Exception as e:
            self._logger.error(f"{e}")
            raise e

    async def get_job(self, job_id: str) -> JobData:
        if type(job_id) is not str:
            job_id = str(job_id)

        try:
            ap_job = self._async_scheduler.get_job(job_id)
            job = await self._job_model.get_one({"job_id": job_id})
            job.next_run_time = ap_job.next_run_time

            return self._job_data_model.from_db_model(job)
        except IndexError:
            self._logger.error("Job is not found!")
            raise IndexError("Job is not found!")
        except Exception as e:
            self._logger.error(f"{e}")
            raise e
    
    async def get_running_jobs(self, 
                               skip: Optional[int] = 0,
                               limit: Optional[int] = 0) -> List[JobData]:
        try:
            ap_jobs = self._async_scheduler.get_jobs()
            query = {"job_id": {"$in": [job.id for job in ap_jobs]}}
            jobs = await self._job_model.get(query)

            return [self._job_data_model.from_db_model(job)
                    for job in jobs]
        except Exception as e:
            self._logger.error(f"{e}")
            raise e

    def start(self) -> None:
        self._async_scheduler.start()


if __name__ == "__main__":
    import asyncio
    import uvloop
    from pytz import utc
    from ..db.client import create_client
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.jobstores.mongodb import MongoDBJobStore
    from apscheduler.executors.asyncio import AsyncIOExecutor
    from apscheduler.executors.pool import (
        ThreadPoolExecutor, ProcessPoolExecutor
    )
    import string
    import random
    import time
    from functools import partial
    import logging

    logging.basicConfig(format="%(asctime)s | %(levelname)s | %(funcName)s |%(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S%z")
    logging.getLogger('apscheduler').setLevel(logging.DEBUG)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)


    def create_scheduler():
        jobstores = {
            'default': MongoDBJobStore(client=db_client.delegate)
        }
        executors = {
            'default': AsyncIOExecutor(),
            'processpool': ProcessPoolExecutor(5)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        return AsyncIOScheduler(
            jobstores=jobstores, executors=executors,
            job_defaults=job_defaults, timezone=utc
        )


    async def simple_test_job():
        logger.info("inside of simple_test_job")
        print("started!")
        print("working...!")
        await asyncio.sleep(5)
        print("finished!")

    async def simple_external_test():
        logger.info("inside of simple_external_test")
        print("working outside of job service.")
        print("started!")
        print("working...!")
        await asyncio.sleep(5)
        print("finished!")


    
    async def job_func():
        job_id = random.randint(0,100)
        print_stuff = ''.join(random.choices(
            string.ascii_uppercase + string.digits, k=job_id))
        sleep_time = random.randint(0,10)
        logger.info(f"inside test job {job_id}")
        print(f"I am job {job_id}")
        print(print_stuff)
        print("started!")
        print("working...!")
        await asyncio.sleep(sleep_time)
        print("finished!")

    
    async def test_add_job(async_job_service: AsyncJobService, jobs: List[Callable]):
        # Pitfall! You should never create a local function as a job function
        # The apscheduler will not be able to resolve its caller.
        # Pass them as argument instead.
        print("\n****************")
        logger.info("Test adding....")
        try:
            # test add
            for job_func in jobs:
                job = await async_job_service.add_job(
                    func=job_func, trigger='interval', seconds=10)
                logger.info(f"get response from async_job_service: {job}")
                assert job is not None
            logger.info("Test adding passed!")
            print("****************\n")
        except AssertionError:
            logger.error(
                f"Excepted job not to be null.")
            print("****************\n")

    # get test
    async def test_get_jobs(async_job_service: AsyncJobService, jobs: List[Callable]):
        print("\n****************")
        logger.info("Test getting jobs....")
        try:
            running_jobs = await async_job_service.get_running_jobs()
            logger.debug(f"Added jobs are {running_jobs}")
            assert len(running_jobs) >= 0
            logger.info("Test get_jobs passed!")
            print("****************\n")
        except AssertionError:
            logger.error(f"Excepted add {len(jobs)} jobs. "
                         f"Added {len(running_jobs)} jobs instead.")
            logger.debug(f"added_jobs: {jobs}")
            print("****************\n")
    
    # update test
    async def test_update_job_attributes(async_job_service):
        print("\n****************")
        logger.info("Test update job names and descriptions")

        try:
            running_jobs = await async_job_service.get_running_jobs()
            logger.debug(f"Added jobs are {running_jobs}")

            for job in running_jobs:
                logger.debug(f"before update: {job}")
                await async_job_service.update_job(
                                        job.job_id,
                                        name=f"updated_{job.name}",
                                        description=f"updated_{job.description}")
                assert len(running_jobs) > 0
                updated_job = await async_job_service.get_job(job_id=job.job_id)
                assert updated_job.name.startswith("updated_")
                assert updated_job.description.startswith("updated_")
                logger.info("Test update_jobs passed!")
                print("****************\n")
        except AssertionError as e:
            logging.error("modification failed!")
            # logger.debug(f"added_jobs: {response}")
            logger.debug(f"updated: {updated_job}")
            print("****************\n")
            raise e

    # update test
    async def test_reschedule_job(async_job_service):
        print("\n****************")
        logger.info("Test reschedule jobs")

        try:
            running_jobs = await async_job_service.get_running_jobs()
            logger.debug(f"Added jobs are {running_jobs}")

            for job in running_jobs:
                logger.debug(f"before update: {job}")
                logging.info(f"type job_id: {type(job.job_id)}")
                updated_jobs = await async_job_service.reschedule_job(
                                        job.job_id, day_of_week='mon-fri',
                                        hour=random.randint(0, 11),
                                        minute=random.randint(1, 59))
                assert updated_jobs is not None
                logger.debug(f"updated job: {updated_jobs}!!!")
                logger.info("Test reschedule passed!")
        except AssertionError as e:
            logging.error("Reschedule failed!")
            logger.debug(f"added_jobs: {updated_jobs}")
            print("****************\n")
            raise e


    # delete test
    async def test_delete_jobs(async_job_service):
        print("\n****************")
        logger.info("Test delete jobs")

        try:
            running_jobs = await async_job_service.get_running_jobs()
            logger.debug(f"Added jobs are {running_jobs}")

            for job in running_jobs:
                await async_job_service.delete_job(job_id=job.job_id)
                logger.debug(f"successfully deleted job {job.job_id}")

            running_jobs = await async_job_service.get_running_jobs()
            assert len(running_jobs) == 0
            logger.info("Test delete passed!")
            print("****************\n")

        except AssertionError:
            logger.debug(f"added_jobs: {running_jobs}")
            print("****************\n")
    
    async def wait_for_tasks(seconds):
        await asyncio.sleep(seconds)
    
    async def clean_up(db_client):
        await db_client.spiderDB.Job.drop()
        await db_client.apscheduler.jobs.drop()


    db_client = create_client(host='localhost',
                              username='admin',
                              password='root',
                              port=27017,
                              db_name='spiderDB')
    async_scheduler = create_scheduler()
    async_scheduler.start()
    
    Job.db = db_client['spiderDB']


    loop = asyncio.get_event_loop()
    async_job_service = AsyncJobService(async_scheduler=async_scheduler)
    test_jobs = [job_func for i in range(2)]

    # print(test_jobs)
    test_cases = [
        test_add_job(
            async_job_service,
            test_jobs),
        test_get_jobs(
            async_job_service,
            test_jobs),
        test_update_job_attributes(async_job_service),
        test_reschedule_job(async_job_service),
        test_delete_jobs(async_job_service),
    ]

    try:
        for test_case in test_cases:
            loop.run_until_complete(test_case)
            time.sleep(2)
        loop.run_until_complete(wait_for_tasks(10))
    except Exception as e:
        print(e)
    finally:
        loop.run_until_complete(clean_up(db_client))

