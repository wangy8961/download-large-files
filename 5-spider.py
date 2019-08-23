import click
from functools import partial
import os
import time
from tqdm import tqdm
from custom_request import custom_request
from logger import logger


def _fetchByRange(url, filename, part_number, start, stop):
    '''根据 HTTP headers 中的 Range 只下载一个块 (rb+ 模式)
    url: 远程目标文件的 URL 地址
    filename: 保存到此文件
    part_number: 块编号(从 0 开始)
    start: 块的起始位置
    stop: 块的结束位置
    '''
    headers = {'Range': 'bytes=%d-%d' % (start, stop)}
    r = custom_request('GET', url, info='Range: bytes={}-{}'.format(start, stop), headers=headers)

    part_length = stop - start + 1
    if not r or len(r.content) != part_length:  # 请求失败时，r 为 None; 或者，突然网络故障了，连接被服务器强制关闭了，此时客户端读取的响应体的长度不足
        logger.error('Part Number {} [Range: bytes={}-{}] download failed'.format(part_number, start, stop))
        return {
            'failed': True  # 用于告知 _fetchByRange() 的调用方，此 Range 下载失败了
        }

    with open(filename, 'rb+') as fp:  # 注意: 不能用 a 模式哦，那样的话就算用 seek(0, 0) 移动指针到文件开头后，还是会从文件末尾处追加
        fp.seek(start)  # 移动文件指针
        logger.debug('File point: {}'.format(fp.tell()))
        fp.write(r.content)  # 写入已下载的字节

    logger.debug('Part Number {} [Range: bytes={}-{}] downloaded'.format(part_number, start, stop))
    return {
        'part': {
            'part_number': part_number,
            'size': len(r.content)
        },
        'failed': False  # 用于告知 _fetchByRange() 的调用方，此 Range 成功下载
    }


@click.command()
@click.option('--dest_filename', type=click.Path(), help="Name of the local destination file with extension")
@click.option('--multipart_chunksize', default=8*1024*1024, help="Size of chunk, unit is bytes")
@click.argument('url', type=click.Path())
def crawl(dest_filename, multipart_chunksize, url):
    t0 = time.time()

    # 如果没有指定本地保存时的文件名，则默认使用 URL 中最后一部分作为文件名
    official_filename = dest_filename if dest_filename else url.split('/')[-1]  # 正式文件名
    temp_filename = official_filename + '.swp'  # 没下载完成时，临时文件名

    # 获取文件的大小
    r = custom_request('HEAD', url, info='header message')
    if not r:  # 请求失败时，r 为 None
        logger.error('Failed to get header message on URL [{}]'.format(url))
        return
    file_size = int(r.headers['Content-Length'])
    logger.info('File size: {} bytes'.format(file_size))

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
        # 获取文件的总块数
        div, mod = divmod(file_size, multipart_chunksize)
        parts_count = div if mod == 0 else div + 1  # 计算出多少个分块
        logger.info('Chunk size: {} bytes, total parts: {}'.format(multipart_chunksize, parts_count))

        # 由于 _fetchByRange() 中使用 rb+ 模式，必须先保证文件存在，所以要先创建指定大小的临时文件 (用0填充)
        f = open(temp_filename, 'wb')
        f.seek(file_size - 1)
        f.write(b'\0')
        f.close()

        # 固定住 url、temp_filename，不用每次都传入相同的参数
        _fetchByRange_partial = partial(_fetchByRange, url, temp_filename)

        # 倒序下载每一个分块 part，假设分块号 part_number 从 0 开始编号
        failed_parts = 0  # 下载失败的分块数目
        with tqdm(total=file_size, unit='B', unit_scale=True, unit_divisor=1024, ascii=True, desc=official_filename) as bar:  # 打印下载时的进度条，并动态显示下载速度
            for part_number in reversed(range(parts_count)):  # 倒序照样能成功下载
                # 重要: 通过块号计算出块的起始与结束位置，最后一块(编号从0开始，所以最后一块编号为 parts_count - 1)需要特殊处理
                if part_number != parts_count-1:
                    start = part_number * multipart_chunksize
                    stop = (part_number + 1) * multipart_chunksize - 1
                else:
                    start = part_number * multipart_chunksize
                    stop = file_size - 1
                result = _fetchByRange_partial(part_number, start, stop)
                if result.get('failed'):
                    failed_parts += 1
                else:
                    bar.update(result.get('part')['size'])

    if failed_parts > 0:
        logger.error('Failed to download {}, failed parts: {}, successful parts: {}'.format(official_filename, failed_parts, parts_count-failed_parts))
    else:
        # 整个文件内容被成功下载后，将临时文件名修改回正式文件名、删除配置文件
        os.rename(temp_filename, official_filename)
        logger.info('{} downloaded'.format(official_filename))
    logger.info('Cost {:.2f} seconds'.format(time.time() - t0))


if __name__ == '__main__':
    crawl()
