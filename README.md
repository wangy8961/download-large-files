# [Python 3 爬虫｜第12章：并发下载大文件 支持断点续传](https://madmalls.com/blog/post/download-large-files/)


# 1. 顺序下载大文件的所有字节

- `1-spider.py`： 下载 `单个` 大文件，不支持断点续传
- `2-spider.py`： 下载 `单个` 大文件，支持断点续传
- `3-spider.py`： 下载 `多个` 大文件，每个线程下载一个文件
- `4-spider.py`： 下载 `多个` 大文件，每个协程下载一个文件


# 2. 乱序下载大文件的各个分段

将大文件按 `multipart_chunksize` 划分成多个分段，分段编号从 `0` 开始，除了最后一个分段以外，其它分段的大小都是 multipart_chunksize 个字节，类似于 `迅雷下载`

- `5-spider.py`： 验证 `乱序` 下载各分段是否最终 SHA256 一致
- `6-spider.py`： 下载 `单个` 大文件，每个线程下载一个分段
- `7-spider.py`： 下载 `单个` 大文件，每个协程下载一个分段
- `8-spider.py`： 下载 `多个` 大文件，每个文件开启一个线程，文件中的各个分段又用多线程去并发
- `9-spider.py`： 下载 `多个` 大文件，每个文件开启一个协程，文件中的各个分段又用协程去并发


# 3. 完整爬虫系列

- [Python 3 爬虫｜第1章：I/O Models 阻塞/非阻塞 同步/异步](https://madmalls.com/blog/post/io-models/)
- [Python 3 爬虫｜第2章：Python 并发编程](https://madmalls.com/blog/post/concurrent-programming-for-python/)
- [Python 3 爬虫｜第3章：同步阻塞下载](https://madmalls.com/blog/post/sequential-download-for-python/)
- [Python 3 爬虫｜第4章：多进程并发下载](https://madmalls.com/blog/post/multi-process-for-python3/)
- [Python 3 爬虫｜第5章：多线程并发下载](https://madmalls.com/blog/post/multi-thread-for-python/)
- [Python 3 爬虫｜第6章：可迭代对象 / 迭代器 / 生成器](https://madmalls.com/blog/post/iterable-iterator-and-generator-in-python/)
- [Python 3 爬虫｜第7章：协程 Coroutines](https://madmalls.com/blog/post/coroutine-in-python/)
- [Python 3 爬虫｜第8章：使用 asyncio 模块实现并发](https://madmalls.com/blog/post/asyncio-howto-in-python3/)
- [Python 3 爬虫｜第9章：使用 asyncio + aiohttp 并发下载](https://madmalls.com/blog/post/aiohttp-howto-in-python3/)
- [Python 3 爬虫｜第10章：爬取少量妹子图](https://madmalls.com/blog/post/python3-concurrency-pics-01/)
- [Python 3 爬虫｜第11章：爬取海量妹子图](https://madmalls.com/blog/post/python3-concurrency-pics-02/)
- [Python 3 爬虫｜第12章：并发下载大文件 支持断点续传](https://madmalls.com/blog/post/download-large-files/)
