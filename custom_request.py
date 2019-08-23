import requests
from logger import logger


def custom_request(method, url, info='common url', *args, **kwargs):
    '''捕获 requests.request() 方法的异常，比如连接超时、被拒绝等
    如果请求成功，则返回响应体；如果请求失败，则返回 None，所以在调用 custom_request() 函数时需要先判断返回值
    '''
    s = requests.session()
    s.keep_alive = False

    try:
        resp = requests.request(method, url, *args, **kwargs)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as errh:
        # In the event of the rare invalid HTTP response, Requests will raise an HTTPError exception (e.g. 401 Unauthorized)
        logger.error('Unsuccessfully get {} [{}], HTTP Error: {}'.format(info, url, errh))
        pass
    except requests.exceptions.ConnectionError as errc:
        # In the event of a network problem (e.g. DNS failure, refused connection, etc)
        logger.error('Unsuccessfully get {} [{}], Connecting Error: {}'.format(info, url, errc))
        pass
    except requests.exceptions.Timeout as errt:
        # If a request times out, a Timeout exception is raised. Maybe set up for a retry, or continue in a retry loop
        logger.error('Unsuccessfully get {} [{}], Timeout Error: {}'.format(info, url, errt))
        pass
    except requests.exceptions.TooManyRedirects as errr:
        # If a request exceeds the configured number of maximum redirections, a TooManyRedirects exception is raised. Tell the user their URL was bad and try a different one
        logger.error('Unsuccessfully get {} [{}], Redirect Error: {}'.format(info, url, errr))
        pass
    except requests.exceptions.RequestException as err:
        # catastrophic error. bail.
        logger.error('Unsuccessfully get {} [{}], Else Error: {}'.format(info, url, err))
        pass
    except Exception as err:
        logger.error('Unsuccessfully get {} [{}], Exception: {}'.format(info, url, err.__class__))
        pass
    else:
        return resp
