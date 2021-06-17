from abc import ABC
from typing import Any, List, Tuple, TypeVar
from .request_client import RequestClient
from ..enums import RequestStatus
from asyncio import TimeoutError
from .parser import ParserContext
from ..models.data_models import (
    ParseRule, ParseResult
)
from concurrent.futures import ProcessPoolExecutor

class BaseSpider(ABC):

    def fetch(self, url: str, params: dict = {}):
        return NotImplemented

    def parse(self, text: str, rules: List[ParseRule]) -> List[ParseResult]:
        return NotImplemented

Spider = TypeVar("Spider")

class Spider(BaseSpider):
    """ Core Spider Class for fetching web pages """

    def __init__(self, request_client: RequestClient, url_to_request: str = ""):
        self._request_client = request_client
        self._request_status = None
        self._url = url_to_request
        self._result = ""

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, value):
        self._result = value

    @property
    def request_status(self):
        return self._request_status

    @request_status.setter
    def request_status(self, value):
        self._request_status = value

    @classmethod
    def create_from_urls(cls, urls: List[str], request_client: RequestClient) -> List[Spider]:
        return [cls(request_client, url) for url in urls]

    def __repr__(self):
        if len(self._result):
            return f"<Spider request_status={self._request_status} result={self._result[:30]}>"
        else:
            return f"<Spider request_status={self._request_status}>"

    async def fetch(self, url: str = "", params: dict={}) -> Tuple[str, str]:
        """ Fetch a web page

        Args:
            url: str
            params: dict, Additional parameters to pass to request

        Returns:
            url
            result
        """
        assert len(self._url) > 0 or len(url) > 0
        url_to_request = url if len(url) > 0 else self._url
        
        try:
            # async with self._request_client:
            async with self._request_client.get(url_to_request, params=params) as response:
                self._request_status = RequestStatus.from_status_code(response.status)
                self._result = await response.text()

        except TimeoutError as e:
            self._request_status = RequestStatus.TIMEOUT
        except Exception as e:
            print(e)
            raise e
        #     self._request_status = RequestStatus.CLIENT_ERROR

        return url, self._result


class WebSpider(BaseSpider):
    """ WebSpider uses a local parser to parse links and web contents.
    """

    def __init__(self, request_client: RequestClient, parser: ParserContext,
                 process_executor: ProcessPoolExecutor):
        self._request_client = request_client
        self._request_status = None
        self._parser = parser
        self._process_executor = process_executor
        self._result = ""

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, value):
        self._result = value

    @property
    def request_status(self):
        return self._request_status

    @request_status.setter
    def request_status(self, value):
        self._request_status = value

    def __repr__(self):
        if len(self._result):
            return f"<Spider request_status={self._request_status} result={self._result[:30]}>"
        else:
            return f"<Spider request_status={self._request_status}>"

    async def fetch(self, url: str, params: dict = {}) -> Tuple[str, str]:
        """ Fetch a web page

        Args:
            url: str
            params: dict, Additional parameters to pass to request

        Returns:
            url
            result
        """
        try:
            async with self._request_client.get(url, params=params) as response:
                self._request_status = RequestStatus.from_status_code(
                    response.status)
                self._result = await response.text()

        except TimeoutError as e:
            self._request_status = RequestStatus.TIMEOUT

        return url, self._result

    async def parse(self, text: str, rules: List[ParseRule]) -> List[ParseResult]:
        return self._parser.parse(text, rules)
    

if __name__ == "__main__":
    import aiohttp
    import asyncio
    import time

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36'
    }
    cookies = {'cookies_are': 'working'}

    def timeit(func):
        async def process(func, *args, **params):
            if asyncio.iscoroutinefunction(func):
                print('this function is a coroutine: {}'.format(func.__name__))
                return await func(*args, **params)
            else:
                print('this is not a coroutine')
                return func(*args, **params)

        async def helper(*args, **params):
            print('{}.time'.format(func.__name__))
            start = time.time()
            result = await process(func, *args, **params)

            # Test normal function route...
            # result = await process(lambda *a, **p: print(*a, **p), *args, **params)

            print('>>>', time.time() - start)
            return result

        return helper

    @timeit
    async def run_spider(urls, headers, cookies):

        async def gather_with_concurrency(n, *tasks):
            semaphore = asyncio.Semaphore(n)

            async def sem_task(task):
                async with semaphore:
                    return await task
            return await asyncio.gather(*(sem_task(task) for task in tasks))


        async with aiohttp.ClientSession(headers=headers, cookies=cookies) as client:
            spiders = Spider.create_from_urls(urls, client)
            print(spiders)
            html_pages = await gather_with_concurrency(2, *[spider.fetch() for spider in spiders])
            print(html_pages)
        
        return spiders, html_pages

    for MAX_PAGE in range(10, 20, 10):
        time.sleep(1)
        print(f"scraping page: {MAX_PAGE}")
        urls = [
            f"https://www.baidu.com/s?wd=aiohttp&pn={page}"
            for page in range(MAX_PAGE)
        ]

        spiders, result = asyncio.run(run_spider(urls, headers, cookies))
        print(result)
