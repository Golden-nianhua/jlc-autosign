# -*- coding: UTF-8 -*-

import os
import random
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import requests
from requests.exceptions import RequestException

try:
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    webdriver = None
    ActionChains = None
    Options = None
    By = None
    EC = None
    WebDriverWait = None


TOKEN_LIST = os.getenv("TOKEN_LIST", "")
SEND_KEY_LIST = os.getenv("SEND_KEY_LIST", "")
JLC_USERNAME = os.getenv("JLC_USERNAME", "")
JLC_PASSWORD = os.getenv("JLC_PASSWORD", "")
ENABLE_BROWSER_LOGIN = os.getenv("ENABLE_BROWSER_LOGIN", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

REQUEST_TIMEOUT = 15
GOLD_SIGN_URL = "https://m.jlc.com/api/activity/sign/signIn?source=3"
GOLD_ASSET_URL = "https://m.jlc.com/api/appPlatform/center/assets/selectPersonalAssetsInfo"
SEVENTH_DAY_URL = "https://m.jlc.com/api/activity/sign/receiveVoucher"
OSHWHUB_SIGN_URL = "https://oshwhub.com/sign_in"


def configure_console_encoding():
    """优先使用 UTF-8 输出，避免本地终端因为 emoji 报编码错误。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def split_env_list(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def mask_account(account):
    if not account:
        return "****"
    if len(account) >= 6:
        return account[:2] + "****" + account[-2:]
    if len(account) >= 4:
        return account[:1] + "***" + account[-1:]
    return "****"


def compact_error(exc):
    message = str(exc).strip().replace("\n", " ")
    return message[:160] if message else exc.__class__.__name__


@dataclass
class AccountConfig:
    index: int
    send_key: str = ""
    access_token: str = ""
    username: str = ""
    password: str = ""


@dataclass
class FeatureResult:
    name: str
    status: str
    message: str


@dataclass
class TokenCheckResult:
    valid: bool
    expired: bool
    message: str
    asset_data: dict
    masked_account: str


def build_token_fallback_results(account, primary_message, fallback_reason):
    results = [
        FeatureResult(
            name="oshwhub",
            status="error",
            message=primary_message,
        )
    ]

    if account.access_token:
        results.append(
            FeatureResult(
                name="fallback",
                status="warning",
                message=(
                    f"金豆签到：检测到账号 {account.index} 的账号密码流程失败，"
                    f"已自动回退到对应 TOKEN_LIST。原因：{fallback_reason}"
                ),
            )
        )
        results.append(sign_gold_bean(account.access_token, account.index))
    else:
        results.append(
            FeatureResult(
                name="gold",
                status="error",
                message=(
                    f"金豆签到：账号 {account.index} 的账号密码流程失败，"
                    "且未配置对应 TOKEN_LIST，无法回退执行"
                ),
            )
        )

    return results


def build_accounts():
    token_list = split_env_list(TOKEN_LIST)
    send_key_list = split_env_list(SEND_KEY_LIST)
    username_list = split_env_list(JLC_USERNAME)
    password_list = split_env_list(JLC_PASSWORD)

    if username_list and len(username_list) != len(password_list):
        log("⚠️ JLC_USERNAME 与 JLC_PASSWORD 数量不一致，不完整的开源平台账号将被跳过")

    if token_list and send_key_list and len(token_list) != len(send_key_list):
        log("⚠️ TOKEN_LIST 与 SEND_KEY_LIST 数量不一致，将按索引匹配；缺少 SendKey 的账号不会推送通知")

    if username_list and send_key_list and len(username_list) != len(send_key_list):
        log("⚠️ JLC_USERNAME 与 SEND_KEY_LIST 数量不一致，将按索引匹配；缺少 SendKey 的账号不会推送通知")

    total_accounts = max(
        len(token_list),
        len(send_key_list),
        len(username_list),
        len(password_list),
    )

    accounts = []
    for i in range(total_accounts):
        account = AccountConfig(
            index=i + 1,
            send_key=send_key_list[i] if i < len(send_key_list) else "",
            access_token=token_list[i] if i < len(token_list) else "",
            username=username_list[i] if i < len(username_list) else "",
            password=password_list[i] if i < len(password_list) else "",
        )

        if account.access_token or account.username or account.password:
            accounts.append(account)

    return accounts


def send_msg_by_server(send_key, title, content):
    push_url = f"https://sctapi.ftqq.com/{send_key}.send"
    data = {
        "text": title,
        "desp": content,
    }
    try:
        response = requests.post(push_url, data=data, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except RequestException as exc:
        log(f"❌ SendKey {send_key[:5]}... 推送失败: {compact_error(exc)}")
        return None


def gold_sign_headers(access_token):
    return {
        "X-JLC-AccessToken": access_token,
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 "
            "(Immersed/20) JlcMobileApp"
        ),
    }


def is_token_expired_message(message):
    text = (message or "").lower()
    keywords = [
        "token",
        "登录",
        "失效",
        "过期",
        "invalid",
        "expired",
        "unauthorized",
        "forbidden",
        "请先登录",
    ]
    return any(keyword in text for keyword in keywords)


def validate_access_token(access_token, account_index):
    headers = gold_sign_headers(access_token)
    masked_account = mask_account(access_token)

    try:
        response = requests.get(GOLD_ASSET_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        status_code = response.status_code

        try:
            result = response.json()
        except ValueError:
            result = {}

        data = result.get("data") or {}
        customer_code = data.get("customerCode")
        if customer_code:
            masked_account = mask_account(customer_code)

        if status_code in (401, 403):
            log(f"账号 {account_index} - ❌ [Token {masked_account}] 已失效，HTTP {status_code}")
            return TokenCheckResult(
                valid=False,
                expired=True,
                message="Token状态：已失效，请重新抓取 X-JLC-AccessToken",
                asset_data=data,
                masked_account=masked_account,
            )

        if customer_code or "integralVoucher" in data:
            log(f"账号 {account_index} - ✅ [Token {masked_account}] 状态正常")
            return TokenCheckResult(
                valid=True,
                expired=False,
                message="Token状态：有效，可用于积分/金豆签到",
                asset_data=data,
                masked_account=masked_account,
            )

        message = result.get("message") or result.get("msg") or f"HTTP {status_code}"
        expired = is_token_expired_message(message)
        if expired:
            log(f"账号 {account_index} - ❌ [Token {masked_account}] 疑似失效: {message}")
            return TokenCheckResult(
                valid=False,
                expired=True,
                message=f"Token状态：已失效或疑似失效，请重新抓取 X-JLC-AccessToken；返回信息：{message}",
                asset_data=data,
                masked_account=masked_account,
            )

        log(f"账号 {account_index} - ⚠️ [Token {masked_account}] 状态检测失败: {message}")
        return TokenCheckResult(
            valid=False,
            expired=False,
            message=f"Token状态：检测失败，返回信息：{message}",
            asset_data=data,
            masked_account=masked_account,
        )
    except RequestException as exc:
        log(f"账号 {account_index} - ⚠️ [Token {masked_account}] 状态检测请求失败: {compact_error(exc)}")
        return TokenCheckResult(
            valid=False,
            expired=False,
            message=f"Token状态：检测失败，网络请求异常：{compact_error(exc)}",
            asset_data={},
            masked_account=masked_account,
        )


def get_gold_asset_info(headers):
    response = requests.get(GOLD_ASSET_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    result = response.json()
    return result.get("data") or {}


def format_gold_message(completed, gain_num, current_total, note):
    current_text = current_total if current_total is not None else "未知"
    return (
        f"积分/金豆签到：{note}；"
        f"是否已完成签到：{'是' if completed else '否'}；"
        f"签到获得金豆：{gain_num}；"
        f"当前金豆：{current_text}"
    )


def sign_gold_bean(access_token, account_index, initial_asset_data=None):
    headers = gold_sign_headers(access_token)
    masked_account = mask_account(access_token)
    integral_voucher = None

    try:
        asset_data = initial_asset_data or get_gold_asset_info(headers)

        customer_code = asset_data.get("customerCode") or access_token
        masked_account = mask_account(customer_code)
        integral_voucher = asset_data.get("integralVoucher", 0)

        sign_response = requests.get(GOLD_SIGN_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        sign_response.raise_for_status()
        sign_result = sign_response.json()

        if not sign_result.get("success"):
            message = sign_result.get("message", "未知错误")
            if "已经签到" in message:
                log(f"账号 {account_index} - ℹ️ [金豆 {masked_account}] 今日已签到")
                return FeatureResult(
                    name="gold",
                    status="already",
                    message=format_gold_message(
                        completed=True,
                        gain_num=0,
                        current_total=integral_voucher,
                        note="今日已签到",
                    ),
                )

            log(f"账号 {account_index} - ❌ [金豆 {masked_account}] 签到失败: {message}")
            return FeatureResult(
                name="gold",
                status="error",
                message=format_gold_message(
                    completed=False,
                    gain_num=0,
                    current_total=integral_voucher,
                    note=f"签到失败，{message}",
                ),
            )

        data = sign_result.get("data") or {}
        gain_num = data.get("gainNum")
        status = data.get("status")

        if status and status > 0:
            if gain_num not in (None, 0):
                try:
                    total = get_gold_asset_info(headers).get("integralVoucher", integral_voucher + gain_num)
                except RequestException:
                    total = integral_voucher + gain_num
                log(f"账号 {account_index} - ✅ [金豆 {masked_account}] 签到成功，获得 {gain_num} 个金豆")
                return FeatureResult(
                    name="gold",
                    status="success",
                    message=format_gold_message(
                        completed=True,
                        gain_num=gain_num,
                        current_total=total,
                        note="签到成功",
                    ),
                )

            seventh_response = requests.get(SEVENTH_DAY_URL, headers=headers, timeout=REQUEST_TIMEOUT)
            seventh_response.raise_for_status()
            seventh_result = seventh_response.json()

            if seventh_result.get("success"):
                try:
                    total = get_gold_asset_info(headers).get("integralVoucher", integral_voucher + 8)
                except RequestException:
                    total = integral_voucher + 8
                log(f"账号 {account_index} - 🎉 [金豆 {masked_account}] 第七天签到成功")
                return FeatureResult(
                    name="gold",
                    status="success",
                    message=format_gold_message(
                        completed=True,
                        gain_num=8,
                        current_total=total,
                        note="第七天签到成功",
                    ),
                )

            message = seventh_result.get("message", "未获取到额外奖励")
            log(f"账号 {account_index} - ⚠️ [金豆 {masked_account}] 第七天奖励领取失败: {message}")
            return FeatureResult(
                name="gold",
                status="error",
                message=format_gold_message(
                    completed=True,
                    gain_num=0,
                    current_total=integral_voucher,
                    note=f"第七天奖励领取失败，{message}",
                ),
            )

        log(f"账号 {account_index} - ℹ️ [金豆 {masked_account}] 今日已签到或暂无奖励")
        return FeatureResult(
            name="gold",
            status="already",
            message=format_gold_message(
                completed=True,
                gain_num=0,
                current_total=integral_voucher,
                note="今日已签到或暂无奖励",
            ),
        )

    except RequestException as exc:
        log(f"账号 {account_index} - ❌ [金豆 {masked_account}] 网络请求失败: {compact_error(exc)}")
        return FeatureResult(
            name="gold",
            status="error",
            message=format_gold_message(
                completed=False,
                gain_num=0,
                current_total=integral_voucher,
                note=f"网络请求失败，{compact_error(exc)}",
            ),
        )
    except KeyError as exc:
        log(f"账号 {account_index} - ❌ [金豆 {masked_account}] 数据解析失败: 缺少键 {exc}")
        return FeatureResult(
            name="gold",
            status="error",
            message=format_gold_message(
                completed=False,
                gain_num=0,
                current_total=integral_voucher,
                note=f"数据解析失败，缺少键 {exc}",
            ),
        )
    except Exception as exc:
        log(f"账号 {account_index} - ❌ [金豆 {masked_account}] 未知错误: {compact_error(exc)}")
        return FeatureResult(
            name="gold",
            status="error",
            message=format_gold_message(
                completed=False,
                gain_num=0,
                current_total=integral_voucher,
                note=f"未知错误，{compact_error(exc)}",
            ),
        )


def create_browser():
    if webdriver is None:
        raise RuntimeError("未安装 selenium，请先执行 pip install -r requirements.txt")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    chrome_bin = os.getenv("CHROME_BIN", "").strip()
    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    user_data_dir = tempfile.mkdtemp(prefix="autosign-")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver, user_data_dir


def extract_access_token_from_local_storage(driver, account_index):
    try:
        key_candidates = [
            "X-JLC-AccessToken",
            "x-jlc-accesstoken",
            "accessToken",
            "token",
            "jlc-token",
        ]

        for key in key_candidates:
            token = driver.execute_script(f"return window.localStorage.getItem('{key}');")
            if token:
                log(f"账号 {account_index} - ✅ 从 localStorage 的 {key} 提取到 AccessToken")
                return token

        log(f"账号 {account_index} - ⚠️ 未在 localStorage 中找到 AccessToken")
        return None
    except Exception as exc:
        log(f"账号 {account_index} - ❌ 提取 AccessToken 失败: {compact_error(exc)}")
        return None


def navigate_and_prepare_m_jlc(driver, wait, account_index):
    log(f"账号 {account_index} - 开始进入 m.jlc.com 准备金豆签到")
    driver.get("https://m.jlc.com/")
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(10)

    try:
        driver.execute_script("window.scrollTo(0, 300);")
        time.sleep(2)

        nav_selectors = [
            "//div[contains(text(), '我的')]",
            "//div[contains(text(), '个人中心')]",
            "//div[contains(text(), '用户中心')]",
            "//a[contains(@href, 'user')]",
            "//a[contains(@href, 'center')]",
            "//div[@class='tabbar']//div[contains(text(), '我的')]",
            "//div[@class='footer']//div[contains(text(), '我的')]",
        ]

        for selector in nav_selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                element.click()
                log(f"账号 {account_index} - 点击导航元素触发登录态同步: {selector}")
                time.sleep(3)
                break
            except Exception:
                continue

        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2)
        driver.refresh()
        time.sleep(5)
    except Exception as exc:
        log(f"账号 {account_index} - ⚠️ m.jlc.com 页面交互异常: {compact_error(exc)}")


def get_browser_access_token(driver, wait, account_index):
    navigate_and_prepare_m_jlc(driver, wait, account_index)
    token = extract_access_token_from_local_storage(driver, account_index)
    if token:
        return token

    try:
        driver.refresh()
        time.sleep(5)
    except Exception:
        pass

    return extract_access_token_from_local_storage(driver, account_index)


def handle_slider_challenge(driver, wait, account_index):
    try:
        slider = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_slide"))
        )
        track = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".nc_scale"))
        )

        track_width = track.size["width"]
        slider_width = slider.size["width"]
        move_distance = max(track_width - slider_width - 10, 0)

        log(f"账号 {account_index} - 检测到滑块验证码，预计滑动距离 {move_distance}px")

        actions = ActionChains(driver)
        actions.click_and_hold(slider).perform()
        time.sleep(0.5)

        quick_steps = int(move_distance * 0.7)
        for i in range(quick_steps):
            if i % 10 == 0:
                time.sleep(0.01)
            actions.move_by_offset(1, 0).perform()

        time.sleep(0.2)

        slow_steps = move_distance - quick_steps
        for i in range(slow_steps):
            if i % 3 == 0:
                time.sleep(0.02)
            y_offset = 1 if i % 2 == 0 else -1 if i % 5 == 0 else 0
            actions.move_by_offset(1, y_offset).perform()

        actions.release().perform()
        time.sleep(5)
        log(f"账号 {account_index} - 滑块拖动完成")
        return True
    except Exception as exc:
        log(f"账号 {account_index} - 滑块验证未触发或处理失败: {compact_error(exc)}")
        return False


def ensure_logged_in(driver, wait, username, password, account_index):
    current_url = driver.current_url
    if "passport.jlc.com/login" not in current_url:
        return True

    log(f"账号 {account_index} - 检测到未登录状态，开始执行登录流程")

    try:
        account_login_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(),"账号登录")]'))
        )
        account_login_button.click()
        time.sleep(2)
    except Exception:
        log(f"账号 {account_index} - 账号登录按钮可能已默认选中")

    try:
        username_input = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, '//input[@placeholder="请输入手机号码 / 客户编号 / 邮箱"]')
            )
        )
        username_input.clear()
        username_input.send_keys(username)

        password_input = wait.until(
            EC.presence_of_element_located((By.XPATH, '//input[@type="password"]'))
        )
        password_input.clear()
        password_input.send_keys(password)
        log(f"账号 {account_index} - 已输入开源平台账号密码")
    except Exception as exc:
        log(f"账号 {account_index} - ❌ 登录输入框未找到: {compact_error(exc)}")
        return False

    try:
        login_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.submit"))
        )
        login_button.click()
        log(f"账号 {account_index} - 已点击登录按钮")
    except Exception as exc:
        log(f"账号 {account_index} - ❌ 登录按钮定位失败: {compact_error(exc)}")
        return False

    time.sleep(8)
    handle_slider_challenge(driver, wait, account_index)

    log(f"账号 {account_index} - 等待登录跳转")
    for _ in range(25):
        current_url = driver.current_url
        if "oshwhub.com" in current_url and "passport.jlc.com" not in current_url:
            log(f"账号 {account_index} - 成功跳转回开源平台签到页面")
            return True
        time.sleep(2)

    log(f"账号 {account_index} - ⚠️ 登录跳转超时")
    return "passport.jlc.com" not in driver.current_url


def sign_oshwhub(driver, wait, account_index, masked_account):
    time.sleep(5)
    try:
        driver.refresh()
        time.sleep(4)
    except Exception:
        pass

    try:
        sign_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//span[contains(text(),"立即签到")]'))
        )
        sign_button.click()
        log(f"账号 {account_index} - ✅ [开源平台 {masked_account}] 签到成功")
        return FeatureResult(
            name="oshwhub",
            status="success",
            message="立创开源平台：签到成功",
        )
    except Exception as sign_exc:
        try:
            driver.find_element(By.XPATH, '//span[contains(text(),"已签到")]')
            log(f"账号 {account_index} - ℹ️ [开源平台 {masked_account}] 今日已签到")
            return FeatureResult(
                name="oshwhub",
                status="already",
                message="立创开源平台：今日已签到",
            )
        except Exception:
            log(f"账号 {account_index} - ❌ [开源平台 {masked_account}] 签到失败")
            return FeatureResult(
                name="oshwhub",
                status="error",
                message=f"立创开源平台：签到失败，{compact_error(sign_exc)}",
            )


def run_browser_driven_signins(account):
    masked_account = mask_account(account.username)
    results = []
    driver = None
    user_data_dir = None

    try:
        driver, user_data_dir = create_browser()
        wait = WebDriverWait(driver, 25)

        log(f"账号 {account.index} - 开始处理账号密码驱动签到，账号 {masked_account}")
        driver.get(OSHWHUB_SIGN_URL)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(10 + random.randint(2, 4))

        if not ensure_logged_in(driver, wait, account.username, account.password, account.index):
            log(f"账号 {account.index} - ⚠️ 浏览器登录失败，回退到对应 TOKEN_LIST 执行金豆签到")
            return build_token_fallback_results(
                account,
                "立创开源平台：账号密码登录失败，请检查账号密码或滑块验证",
                "账号密码登录失败",
            )

        results.append(sign_oshwhub(driver, wait, account.index, masked_account))

        access_token = get_browser_access_token(driver, wait, account.index)
        if access_token:
            token_check = validate_access_token(access_token, account.index)
            results.append(
                FeatureResult(
                    name="token",
                    status="success" if token_check.valid else "error" if token_check.expired else "warning",
                    message=token_check.message,
                )
            )
            if token_check.valid:
                results.append(sign_gold_bean(access_token, account.index, initial_asset_data=token_check.asset_data))
            else:
                results.append(
                    FeatureResult(
                        name="gold",
                        status="error",
                        message=format_gold_message(
                            completed=False,
                            gain_num=0,
                            current_total=None,
                            note="未执行，浏览器提取到的 Token 不可用",
                        ),
                    )
                )
        elif account.access_token:
            log(f"账号 {account.index} - ⚠️ 未提取到浏览器 AccessToken，回退到 TOKEN_LIST 执行金豆签到")
            results.append(
                FeatureResult(
                    name="fallback",
                    status="warning",
                    message=(
                        f"金豆签到：账号 {account.index} 已完成网页登录，但未能从浏览器登录态提取 "
                        "AccessToken，已自动回退到对应 TOKEN_LIST"
                    ),
                )
            )
            results.append(sign_gold_bean(account.access_token, account.index))
        else:
            results.append(
                FeatureResult(
                    name="gold",
                    status="error",
                    message="金豆签到：无法从账号密码登录态提取 AccessToken",
                )
            )

        return results
    except Exception as exc:
        log(f"账号 {account.index} - ❌ [账号密码驱动] 未知错误: {compact_error(exc)}")
        return build_token_fallback_results(
            account,
            f"账号密码驱动流程：未知错误，{compact_error(exc)}",
            f"账号密码驱动流程异常，{compact_error(exc)}",
        )
    finally:
        if driver is not None:
            driver.quit()
            log(f"账号 {account.index} - 浏览器已关闭")
        if user_data_dir:
            shutil.rmtree(user_data_dir, ignore_errors=True)


def run_token_based_signins(account):
    results = []

    if account.username and account.password and not ENABLE_BROWSER_LOGIN:
        results.append(
            FeatureResult(
                name="mode",
                status="info",
                message="账号密码登录：已保留，但当前未启用；本次直接使用 TOKEN_LIST 执行积分/金豆签到",
            )
        )

    token_check = validate_access_token(account.access_token, account.index)
    results.append(
        FeatureResult(
            name="token",
            status="success" if token_check.valid else "error" if token_check.expired else "warning",
            message=token_check.message,
        )
    )

    if token_check.valid:
        results.append(sign_gold_bean(account.access_token, account.index, initial_asset_data=token_check.asset_data))
        return results

    if token_check.expired:
        results.append(
            FeatureResult(
                name="gold",
                status="error",
                message=format_gold_message(
                    completed=False,
                    gain_num=0,
                    current_total=None,
                    note="未执行，Token 已失效，请重新抓取 X-JLC-AccessToken",
                ),
            )
        )
        return results

    results.append(
        FeatureResult(
            name="gold",
            status="error",
            message=format_gold_message(
                completed=False,
                gain_num=0,
                current_total=None,
                note="未执行，Token 状态检测失败，请检查网络或重新抓取 Token",
            ),
        )
    )
    return results


def run_account_signins(account):
    if account.access_token:
        return run_token_based_signins(account)

    if ENABLE_BROWSER_LOGIN and account.username and account.password:
        return run_browser_driven_signins(account)

    if account.username and account.password:
        return [
            FeatureResult(
                name="mode",
                status="skipped",
                message="账号密码登录：已保留，但当前默认未启用；如需启用请设置 ENABLE_BROWSER_LOGIN=true",
            )
        ]

    if account.username or account.password:
        log(f"账号 {account.index} - ⚠️ 开源平台账号密码未成对配置，且当前未使用浏览器登录")
        return [
            FeatureResult(
                name="mode",
                status="skipped",
                message="账号密码登录：已跳过，JLC_USERNAME 与 JLC_PASSWORD 未成对配置，且当前默认仅使用 TOKEN_LIST",
            )
        ]

    return []


def format_account_report(account, results):
    identity = mask_account(account.username or account.access_token or f"账号{account.index}")
    lines = [f"### 账号 {account.index}（{identity}）"]
    for result in results:
        lines.append(f"- {result.message}")
    return "\n".join(lines)


def send_notifications(group_results):
    if not group_results:
        log("ℹ️ 没有可推送的 SendKey 或通知内容，跳过消息推送")
        return

    for send_key, reports in group_results.items():
        content = "\n\n".join(reports)
        log(f"📤 准备向 SendKey {send_key[:5]}... 推送 {len(reports)} 条账号汇总")
        response = send_msg_by_server(send_key, "嘉立创签到汇总", content)

        if response and response.get("code") == 0:
            push_id = response.get("data", {}).get("pushid", "")
            log(f"✅ 通知发送成功，消息ID: {push_id}")
        else:
            error_message = response.get("message") if response else "未知错误"
            log(f"❌ 通知发送失败: {error_message}")


def main():
    configure_console_encoding()
    accounts = build_accounts()

    if not accounts:
        log("❌ 请至少配置 TOKEN_LIST。账号密码方式虽然保留，但当前默认未启用")
        return

    log(f"🔧 共发现 {len(accounts)} 个账号索引需要处理")

    group_results = defaultdict(list)

    for i, account in enumerate(accounts, start=1):
        enabled_features = []
        if account.access_token:
            enabled_features.append("积分/金豆签到（TOKEN_LIST）")
        elif ENABLE_BROWSER_LOGIN and account.username and account.password:
            enabled_features.append("开源平台 + 积分/金豆签到（账号密码驱动）")
        elif account.username and account.password:
            enabled_features.append("账号密码模式已保留但默认未启用")

        feature_text = " + ".join(enabled_features) if enabled_features else "无可用签到功能"
        log(f"🚀 开始处理第 {i}/{len(accounts)} 个账号，功能: {feature_text}")

        results = run_account_signins(account)
        if not results:
            log(f"账号 {account.index} - ⚠️ 没有可执行的签到配置")
            continue

        report = format_account_report(account, results)
        log(f"账号 {account.index} - 汇总结果:\n{report}")

        if account.send_key:
            group_results[account.send_key].append(report)
        else:
            log(f"账号 {account.index} - ⚠️ 未配置 SendKey，本次不会推送通知")

        if i < len(accounts):
            wait_time = random.randint(5, 12)
            log(f"⏳ 等待 {wait_time} 秒后处理下一个账号")
            time.sleep(wait_time)

    log("📬 开始发送签到通知")
    send_notifications(group_results)
    log("🏁 所有签到任务执行完毕")


if __name__ == "__main__":
    main()
