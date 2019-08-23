import asyncio
import aiohttp
import aiofiles
from functools import partial
import json
import os
import time
from tqdm import tqdm
from logger import logger


async def _fetchByRange(semaphore, session, url, temp_filename, config_filename, part_number, start, stop):
    '''根据 HTTP headers 中的 Range 只下载一个块 (rb+ 模式)
    semaphore: 限制并发的协程数
    session: aiohttp 会话
    url: 远程目标文件的 URL 地址
    temp_filename: 临时文件
    config_filename: 配置文件
    part_number: 块编号(从 0 开始)
    start: 块的起始位置
    stop: 块的结束位置
    '''
    part_length = stop - start + 1
    headers = {'Range': 'bytes=%d-%d' % (start, stop)}

    try:
        async with semaphore:
            async with session.get(url, headers=headers) as r:
                # 此分块的信息
                part = {
                    'ETag': r.headers['ETag'],
                    'Last-Modified': r.headers['Last-Modified'],
                    'PartNumber': part_number,
                    'Size': part_length
                }

                async with aiofiles.open(temp_filename, 'rb+') as fp:  # 注意: 不能用 a 模式哦，那样的话就算用 seek(0, 0) 移动指针到文件开头后，还是会从文件末尾处追加
                    await fp.seek(start)  # 移动文件指针
                    logger.debug('[{}] File point: {}'.format(temp_filename.strip('.swp'), fp.tell()))
                    binary_content = await r.read()  # Binary Response Content: access the response body as bytes, for non-text requests
                    await fp.write(binary_content)  # 写入已下载的字节

                # 读取原配置文件中的内容
                f = open(config_filename, 'r')
                cfg = json.load(f)
                f.close()
                # 更新配置文件，写入此分块的信息
                f = open(config_filename, 'w')
                cfg['parts'].append(part)
                json.dump(cfg, f)
                f.close()

                logger.debug('[{}] Part Number {} [Range: bytes={}-{}] downloaded'.format(temp_filename.strip('.swp'), part_number, start, stop))
                return {
                    'part': part,
                    'failed': False  # 用于告知 _fetchByRange() 的调用方，此 Range 成功下载
                }
    except Exception as e:
        logger.error('[{}] Part Number {} [Range: bytes={}-{}] download failed, the reason is that {}'.format(temp_filename.strip('.swp'), part_number, start, stop, e))
        return {
            'failed': True  # 用于告知 _fetchByRange() 的调用方，此 Range 下载失败了
        }


async def _fetchOneFile(session, url, dest_filename=None, multipart_chunksize=8*1024*1024):
    t0 = time.time()

    # 如果没有指定本地保存时的文件名，则默认使用 URL 中最后一部分作为文件名
    official_filename = dest_filename if dest_filename else url.split('/')[-1]  # 正式文件名
    temp_filename = official_filename + '.swp'  # 没下载完成时，临时文件名
    config_filename = official_filename + '.swp.cfg'  # 没下载完成时，存储 ETag 等信息的配置文件名

    # 获取文件的大小和 ETag
    try:
        async with session.head(url) as r:
            file_size = int(r.headers['Content-Length'])
            ETag = r.headers['ETag']
            logger.debug('[{}] file size: {} bytes, ETag: {}'.format(official_filename, file_size, ETag))
    except Exception as e:
        logger.error('Failed to get header message on URL [{}], the reason is that {}'.format(url, e))
        return

    # 如果正式文件存在
    if os.path.exists(official_filename):
        if os.path.getsize(official_filename) == file_size:  # 且大小与待下载的目标文件大小一致时
            logger.warning('The file [{}] has already been downloaded'.format(official_filename))
            return
        else:  # 大小不一致时，提醒用户要保存的文件名已存在，需要手动处理，不能随便覆盖
            logger.warning('The filename [{}] has already exist, but it does not match the remote file'.format(official_filename))
            return

    # 首先需要判断此文件支不支持 Range 下载，请求第 1 个字节即可
    headers = {'Range': 'bytes=0-0'}

    try:
        async with session.head(url, headers=headers) as r:
            if r.status != 206:  # 不支持 Range 下载时
                logger.warning('The file [{}] does not support breakpoint retransmission'.format(official_filename))
                # 需要重新从头开始下载 (wb 模式)
                with tqdm(total=file_size, unit='B', unit_scale=True, unit_divisor=1024, ascii=True, desc=official_filename) as bar:  # 打印下载时的进度条，并动态显示下载速度
                    try:
                        async with session.get(url) as r:
                            async with aiofiles.open(temp_filename, 'wb') as fp:
                                while True:
                                    chunk = await r.content.read(multipart_chunksize)
                                    if not chunk:
                                        break
                                    await fp.write(chunk)
                                    bar.update(len(chunk))
                    except Exception as e:
                        logger.error('Failed to get all content on URL [{}], the reason is that {}'.format(url, e))
                        return
                # 整个文件内容被成功下载后，将临时文件名修改回正式文件名、删除配置文件
                os.rename(temp_filename, official_filename)
                if os.path.exists(config_filename):
                    os.remove(config_filename)
                logger.debug('{} downloaded'.format(official_filename))
                logger.debug('Cost {:.2f} seconds'.format(time.time() - t0))
            else:  # 支持 Range 下载时
                # 获取文件的总块数
                div, mod = divmod(file_size, multipart_chunksize)
                parts_count = div if mod == 0 else div + 1  # 计算出多少个分块
                logger.debug('[{}] Chunk size: {} bytes, total parts: {}'.format(official_filename, multipart_chunksize, parts_count))

                # 如果临时文件存在
                if os.path.exists(temp_filename):
                    if os.path.getsize(temp_filename) != file_size:  # 说明此临时文件有问题，需要先删除它
                        os.remove(temp_filename)
                    else:  # 临时文件有效时
                        if not os.path.exists(config_filename):  # 如果不存在配置文件时
                            os.remove(temp_filename)
                        else:  # 如果配置文件也在，则继续判断 ETag 是否一致
                            with open(config_filename, 'r') as fp:
                                cfg = json.load(fp)
                                if cfg['ETag'] != ETag:  # 如果不一致
                                    os.remove(temp_filename)
                                else:  # 从配置文件中读取已下载的分块号集合，从而得出未下载的分块号集合
                                    succeed_parts = {part['PartNumber'] for part in cfg['parts']}  # 之前已下载好的分块号集合
                                    succeed_parts_size = sum([part['Size'] for part in cfg['parts']])  # 已下载的块的总大小，注意是列表推导式不是集合推导式
                                    parts = set(range(parts_count)) - succeed_parts  # 本次需要下载的分块号集合

                # 再次判断临时文件在不在，如果不存在时，表示要下载所有分块号
                if not os.path.exists(temp_filename):
                    succeed_parts_size = 0
                    parts = range(parts_count)

                    # 由于 _fetchByRange() 中使用 rb+ 模式，必须先保证文件存在，所以要先创建指定大小的临时文件 (用0填充)
                    async with aiofiles.open(temp_filename, 'wb') as fp:
                        await fp.seek(file_size - 1)
                        await fp.write(b'\0')

                    with open(config_filename, 'w') as fp:  # 创建配置文件，写入 ETag
                        cfg = {
                            'ETag': ETag,
                            'parts': []
                        }
                        json.dump(cfg, fp)

                logger.debug('[{}] The remaining parts that need to be downloaded: {}'.format(official_filename, set(parts)))

                # 用于限制并发请求数量
                sem = asyncio.Semaphore(min(64, len(parts)))

                # 固定住 sem、session、url、temp_filename、config_filename，不用每次都传入相同的参数
                _fetchByRange_partial = partial(_fetchByRange, sem, session, url, temp_filename, config_filename)

                to_do = []  # 保存所有任务的列表
                for part_number in parts:
                    # 重要: 通过块号计算出块的起始与结束位置，最后一块(编号从0开始，所以最后一块编号为 parts_count - 1)需要特殊处理
                    if part_number != parts_count-1:
                        start = part_number * multipart_chunksize
                        stop = (part_number + 1) * multipart_chunksize - 1
                    else:
                        start = part_number * multipart_chunksize
                        stop = file_size - 1
                    to_do.append(_fetchByRange_partial(part_number, start, stop))

                to_do_iter = asyncio.as_completed(to_do)

                failed_parts = 0  # 下载失败的分块数目
                with tqdm(total=file_size, initial=succeed_parts_size, unit='B', unit_scale=True, unit_divisor=1024, ascii=True, desc=official_filename) as bar:  # 打印下载时的进度条，并动态显示下载速度
                    for future in to_do_iter:
                        result = await future
                        if result.get('failed'):
                            failed_parts += 1
                        else:
                            bar.update(result.get('part')['Size'])

                if failed_parts > 0:
                    logger.error('Failed to download {}, failed parts: {}, successful parts: {}'.format(official_filename, failed_parts, parts_count-failed_parts))
                else:
                    # 整个文件内容被成功下载后，将临时文件名修改回正式文件名、删除配置文件
                    os.rename(temp_filename, official_filename)
                    if os.path.exists(config_filename):
                        os.remove(config_filename)
                    logger.debug('{} downloaded'.format(official_filename))
                    logger.debug('Cost {:.2f} seconds'.format(time.time() - t0))

    except Exception as e:
        logger.error('Failed to get [Range: bytes=0-0] on URL [{}], the reason is that {}'.format(url, e))
        return


async def crawl(config='config.json'):
    tasks = []  # 保存所有任务的列表
    async with aiohttp.ClientSession() as session:  # aiohttp建议整个应用只创建一个session，不能为每个请求创建一个seesion
        with open(config, 'r') as fp:  # 读取包含多个大文件相关信息(url、dest_filename、multipart_chunksize)的配置文件 config.json
            cfg = json.load(fp)
            for f in cfg['files']:
                task = asyncio.create_task(_fetchOneFile(session, f['url'], f['dest_filename'], f['multipart_chunksize']))  # asyncio.create_task()是Python 3.7新加的，否则使用asyncio.ensure_future()
                tasks.append(task)
            await asyncio.gather(*tasks)
    await session.close()

if __name__ == '__main__':
    t0 = time.time()
    asyncio.run(crawl())
    logger.info('Cost {:.2f} seconds'.format(time.time() - t0))
