# -*- coding: utf-8 -*-

# 打卡脚修改自ZJU-nCov-Hitcarder的开源代码，感谢这位同学开源的代码

import datetime
import json
import logging
import re
import time

import requests
import yagmail

from basic_info import email_server, users


class DaKa(object):
    """Hit card class

    Attributes:
        username: (str) 浙大统一认证平台用户名（一般为学号）
        password: (str) 浙大统一认证平台密码
        login_url: (str) 登录url
        base_url: (str) 打卡首页url
        save_url: (str) 提交打卡url
        sess: (requests.Session) 统一的session
    """

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.login_url = "https://zjuam.zju.edu.cn/cas/login?service=https%3A%2F%2Fhealthreport.zju.edu.cn%2Fa_zju%2Fapi%2Fsso%2Findex%3Fredirect%3Dhttps%253A%252F%252Fhealthreport.zju.edu.cn%252Fncov%252Fwap%252Fdefault%252Findex"
        self.base_url = "https://healthreport.zju.edu.cn/ncov/wap/default/index"
        self.save_url = "https://healthreport.zju.edu.cn/ncov/wap/default/save"
        self.sess = requests.Session()

    def login(self):
        """Login to ZJU platform"""
        res = self.sess.get(self.login_url)
        execution = re.search(
            'name="execution" value="(.*?)"', res.text).group(1)
        res = self.sess.get(
            url='https://zjuam.zju.edu.cn/cas/v2/getPubKey').json()
        n, e = res['modulus'], res['exponent']
        encrypt_password = self._rsa_encrypt(self.password, e, n)

        data = {
            'username': self.username,
            'password': encrypt_password,
            'execution': execution,
            '_eventId': 'submit'
        }
        res = self.sess.post(url=self.login_url, data=data)

        # check if login successfully
        if '统一身份认证' in res.content.decode():
            raise LoginError('登录失败，请核实账号密码重新登录')
        return self.sess

    def post(self):
        """Post the hitcard info"""
        res = self.sess.post(self.save_url, data=self.info)
        return json.loads(res.text)

    def get_date(self):
        """Get current date"""
        today = datetime.date.today()
        return "%4d%02d%02d" % (today.year, today.month, today.day)

    def get_info(self, html=None):
        """Get hitcard info, which is the old info with updated new time."""
        if not html:
            res = self.sess.get(self.base_url)
            html = res.content.decode()

        try:
            old_infos = re.findall(r'oldInfo: ({[^\n]+})', html)
            if len(old_infos) != 0:
                old_info = json.loads(old_infos[0])
            else:
                raise RegexMatchError("未发现缓存信息，请先至少手动成功打卡一次再运行脚本")

            new_info_tmp = json.loads(re.findall(r'def = ({[^\n]+})', html)[0])
            new_id = new_info_tmp['id']
            name = re.findall(r'realname: "([^\"]+)",', html)[0]
            number = re.findall(r"number: '([^\']+)',", html)[0]
        except IndexError:
            raise RegexMatchError('Relative info not found in html with regex')
        except json.decoder.JSONDecodeError:
            raise DecodeError('JSON decode error')

        new_info = old_info.copy()
        new_info['id'] = new_id
        new_info['name'] = name
        new_info['number'] = number
        new_info["date"] = self.get_date()
        new_info["created"] = round(time.time())
        new_info["address"] = "浙江省杭州市西湖区"
        new_info["area"] = "浙江省 杭州市 西湖区"
        new_info["province"] = new_info["area"].split(' ')[0]
        new_info["city"] = new_info["area"].split(' ')[1]
        # form change
        new_info['jrdqtlqk[]'] = 0
        new_info['jrdqjcqk[]'] = 0
        new_info['sfsqhzjkk'] = 1   # 是否申领杭州健康码
        new_info['sqhzjkkys'] = 1   # 杭州健康吗颜色，1:绿色 2:红色 3:黄色
        new_info['sfqrxxss'] = 1    # 是否确认信息属实
        new_info['jcqzrq'] = ""
        new_info['gwszdd'] = ""
        new_info['szgjcs'] = ""
        self.info = new_info
        return new_info

    def _rsa_encrypt(self, password_str, e_str, M_str):
        password_bytes = bytes(password_str, 'ascii')
        password_int = int.from_bytes(password_bytes, 'big')
        e_int = int(e_str, 16)
        M_int = int(M_str, 16)
        result_int = pow(password_int, e_int, M_int)
        return hex(result_int)[2:].rjust(128, '0')


# Exceptions
class LoginError(Exception):
    """Login Exception"""
    pass


class RegexMatchError(Exception):
    """Regex Matching Exception"""
    pass


class DecodeError(Exception):
    """JSON Decode Exception"""
    pass


class EmailBot:

    def __init__(self, to_email, from_email, password, host):
        self.status_enum = {
            "success": {"desc": "成功", "emoji": "✔"},
            "failure": {"desc": "失败", "emoji": "❌"}
        }

        self.subject_prefix = "每日健康打卡: "
        self.to_user = to_email
        self.yag = yagmail.SMTP(user=from_email, password=password, host=host)

    def send_email(self, log, status):
        subject = self.subject_prefix + self.status_enum[status]["desc"]
        contents = log.copy()
        contents.insert(0, self.status_enum[status]["emoji"])
        self.yag.send(self.to_user, subject, contents)

class Log:
    def __init__(self, email_bot: EmailBot):
        logging.basicConfig(
            level=logging.INFO,
            filename="log.txt",
            format="%(message)s")
        self.email_bot = email_bot
        self.start_up()

    def start_up(self):
        now = "[Time] %s" % datetime.datetime.now().strftime(
            '%Y-%m-%d %H:%M:%S')
        self.log_cache = [now]
        logging.info("\n")
        logging.info(now)

    def info(self, contents):
        logging.info(contents)
        self.log_cache.append(contents)

    def warning(self, contents):
        logging.warning(contents)
        self.log_cache.append(contents)

    def error(self, contents):
        logging.error(contents)
        self.log_cache.append(contents)
        self.email_bot.send_email(self.log_cache, "failure")

    def end_with_success(self):
        self.email_bot.send_email(self.log_cache, "success")


def main(email_server, user):
    email_bot = EmailBot(user["TO_EMAIL"], email_server["FROM_EMAIL"],
                         email_server["EMAIL_PASSWD"], email_server["HOST"])
    log = Log(email_bot)
    dk = DaKa(user["ZJU_USERNAME"], user["ZJU_PASSWD"])

    log.info("打卡任务启动")

    log.info("登录到浙大统一身份认证平台...")
    try:
        dk.login()
        log.info("已登录到浙大统一身份认证平台")
    except Exception as err:
        log.error(str(err))
        return

    log.info('正在获取个人信息...')
    try:
        dk.get_info()
        log.info('%s %s同学, 你好~' % (dk.info['number'], dk.info['name']))
    except Exception as err:
        log.error('获取信息失败，请手动打卡，更多信息: ' + str(err))
        return

    try:
        res = dk.post()
        if str(res['e']) == '0':
            log.info('已为您打卡成功！')
        else:
            log.warning(res['m'])
    except Exception:
        log.error('数据提交失败')
        return

    log.end_with_success()


if __name__ == "__main__":
    for name in users:
        main(email_server,users[name])
