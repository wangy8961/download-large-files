import click
import json
import os
import time
from tqdm import tqdm
from custom_request import custom_request
from logger import logger


@click.command()
@click.option('--dest_filename', type=click.Path(), help="Name of the local destination file with extension")
@click.option('--multipart_chunksize', default=8*1024*1024, help="Size of chunk, unit is bytes")
@click.argument('url', type=click.Path())
def crawl(dest_filename, multipart_chunksize, url):
    t0 = time.time()

    # 如果没有指定本地保存时的文件名，则默认使用 URL 中最后一部分作为文件名
    official_filename = dest_filename if dest_filename else url.split('/')[-1]  # 正式文件名
    temp_filename = official_filename + '.swp'  # 没下载完成时，临时文件名
    config_filename = official_filename + '.swp.cfg'  # 没下载完成时，存储 ETag 等信息的配置文件名

    # 获取文件的大小和 ETag
    r = custom_request('HEAD', url, info='header message')
    if not r:  # 请求失败时，r 为 None
        logger.error('Failed to get header message on URL [{}]'.format(url))
        return
    file_size = int(r.headers['Content-Length'])
    ETag = r.headers['ETag']
    logger.info('File size: {} bytes, ETag: {}'.format(file_size, ETag))

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
    r = custom_request('HEAD', url, info='Range: bytes=0-0', headers=headers)
    if not r:  # 请求失败时，r 为 None
        logger.error('Failed to get [Range: bytes=0-0] on URL [{}]'.format(url))
        return

    if r.status_code != 206:  # 不支持 Range 下载时
        logger.warning('The file [{}] does not support breakpoint retransmission'.format(official_filename))
        # 需要重新从头开始下载 (wb 模式)
        with tqdm(total=file_size, unit='B', unit_scale=True, unit_divisor=1024, ascii=True, desc=official_filename) as bar:  # 打印下载时的进度条，并动态显示下载速度
            r = custom_request('GET', url, info='all content', stream=True)
            if not r:  # 请求失败时，r 为 None
                logger.error('Failed to get all content on URL [{}]'.format(url))
                return
            with open(temp_filename, 'wb') as fp:
                for chunk in r.iter_content(chunk_size=multipart_chunksize):
                    if chunk:
                        fp.write(chunk)
                        bar.update(len(chunk))
    else:  # 支持 Range 下载时
        # 如果临时文件存在
        if os.path.exists(temp_filename):
            start = os.path.getsize(temp_filename)  # 获取临时文件的大小
            if start >= file_size:  # 说明此临时文件有问题，需要先删除它
                os.remove(temp_filename)
            else:  # 临时文件有效时(如果用户故意生成同名的临时文件，且大小小于要下载的目标文件的大小时，不考虑这么复杂了...)
                if not os.path.exists(config_filename):  # 如果不存在配置文件时
                    os.remove(temp_filename)
                else:  # 如果配置文件也在，则继续判断 ETag 是否一致
                    with open(config_filename, 'r') as fp:
                        cfg = json.load(fp)
                        if cfg['ETag'] != ETag:  # 如果不一致
                            os.remove(temp_filename)

        # 再次判断临时文件在不在，如果不存在时，表示要从头下载
        if not os.path.exists(temp_filename):
            start = 0
            open(temp_filename, 'a').close()  # 创建空的临时文件
            with open(config_filename, 'w') as fp:  # 创建配置文件，写入 ETag
                cfg = {'ETag': ETag}
                json.dump(cfg, fp)

        # 根据 HTTP headers 中的 Range 只下载文件的部分字节 (ab 模式)
        logger.info('Download from [Range: bytes=%d-]' % start)
        headers = {'Range': 'bytes=%d-' % start}  # start 无需+1，自己体会
        with tqdm(total=file_size, initial=start, unit='B', unit_scale=True, unit_divisor=1024, ascii=True, desc=official_filename) as bar:  # 打印下载时的进度条，并动态显示下载速度
            r = custom_request('GET', url, info='Range: bytes={}-'.format(start), headers=headers, stream=True)
            if not r:  # 请求失败时，r 为 None
                logger.error('Failed to download [Range: bytes={}-] on URL [{}]'.format(start, url))
                return

            with open(temp_filename, 'ab') as fp:
                for chunk in r.iter_content(chunk_size=multipart_chunksize):  # Range 范围可能很大，还是需要按 chunk 依次下载
                    if chunk:
                        fp.write(chunk)
                        bar.update(len(chunk))

    # 整个文件内容被成功下载后，将临时文件名修改回正式文件名、删除配置文件
    if os.path.getsize(temp_filename) == file_size:  # 以防网络故障
        os.rename(temp_filename, official_filename)
        if os.path.exists(config_filename):
            os.remove(config_filename)
        logger.info('{} downloaded'.format(official_filename))
        logger.info('Cost {:.2f} seconds'.format(time.time() - t0))
    else:
        logger.error('Failed to download {}'.format(official_filename))


if __name__ == '__main__':
    crawl()
