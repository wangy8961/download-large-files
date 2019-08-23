import click
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

    # 分块下载，即使文件非常大，也不会撑爆内存
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

    # 整个文件内容被成功下载后，将临时文件名修改回正式文件名
    if os.path.getsize(temp_filename) == file_size:  # 以防网络故障
        os.rename(temp_filename, official_filename)
        logger.info('{} downloaded'.format(official_filename))
        logger.info('Cost {:.2f} seconds'.format(time.time() - t0))
    else:
        logger.error('Failed to download {}'.format(official_filename))


if __name__ == '__main__':
    crawl()
