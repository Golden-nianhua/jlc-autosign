# -*- coding: utf-8 -*-

import sys
import time
from dataclasses import dataclass
from datetime import datetime

import requests

import config

ACCOUNTS = config.ACCOUNTS
SEND_KEY = getattr(config, "SEND_KEY", "")

REQUEST_TIMEOUT = 15
MAX_SIGNIN_RETRIES = 3
GOLD_SIGN_URL = "https://m.jlc.com/api/activity/sign/signIn?source=3"
GOLD_ASSET_URL = "https://m.jlc.com/api/appPlatform/center/assets/selectPersonalAssetsInfo"
SEVENTH_DAY_URL = "https://m.jlc.com/api/activity/sign/receiveVoucher"


@dataclass
class Result:
    status: str
    message: str


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def headers(token):
    return {
        "X-JLC-AccessToken": token,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) JlcMobileApp",
    }


def gold_message(completed, gain, total, note):
    return (
        f"金豆签到：{note}；是否已完成签到：{'是' if completed else '否'}；"
        f"签到获得金豆：{gain}；当前金豆：{total}"
    )


def get_assets(token):
    response = requests.get(GOLD_ASSET_URL, headers=headers(token), timeout=REQUEST_TIMEOUT)
    return response, (response.json().get("data") or {})


def check_token(token):
    response, assets = get_assets(token)
    if response.status_code in (401, 403):
        return None, Result("error", "Token状态：已失效，请重新抓取 X-JLC-AccessToken")

    if assets.get("customerCode") or "integralVoucher" in assets:
        return assets, Result("success", "Token状态：有效，可用于金豆签到")

    message = response.json().get("message") or response.text
    return None, Result("error", f"Token状态：无效，{message}")


def sign_gold(token, assets):
    current_total = assets.get("integralVoucher", 0)
    response = requests.get(GOLD_SIGN_URL, headers=headers(token), timeout=REQUEST_TIMEOUT)
    result = response.json()

    if not result.get("success"):
        message = result.get("message", "未知错误")
        if "已经签到" in message:
            return Result("already", gold_message(True, 0, current_total, "今日已签到"))
        return Result("error", gold_message(False, 0, current_total, f"签到失败，{message}"))

    data = result.get("data") or {}
    if data.get("status", 0) <= 0:
        return Result("already", gold_message(True, 0, current_total, "今日已签到"))

    gain = data.get("gainNum", 0)
    if gain:
        _, latest_assets = get_assets(token)
        return Result(
            "success",
            gold_message(True, gain, latest_assets.get("integralVoucher", current_total + gain), "签到成功"),
        )

    # 第七天奖励需要单独领取。
    reward = requests.get(SEVENTH_DAY_URL, headers=headers(token), timeout=REQUEST_TIMEOUT).json()
    if reward.get("success"):
        _, latest_assets = get_assets(token)
        return Result(
            "success",
            gold_message(True, 8, latest_assets.get("integralVoucher", current_total + 8), "第七天签到成功"),
        )

    return Result("error", gold_message(True, 0, current_total, "第七天奖励领取失败"))


def sign_account(token):
    try:
        assets, token_result = check_token(token)
        results = [token_result]
        if assets:
            results.append(sign_gold(token, assets))
        else:
            results.append(Result("error", gold_message(False, 0, "未知", "未执行，Token 无效")))
        return results
    except requests.RequestException as error:
        return [Result("error", f"金豆签到：网络请求失败，{error}")]


def has_failure(results):
    return any(result.status == "error" for result in results)


def sign_with_retries(token, index):
    # 首次执行失败后，最多额外重试三次。
    for attempt in range(MAX_SIGNIN_RETRIES + 1):
        results = sign_account(token)
        if not has_failure(results):
            if attempt:
                results.append(Result("success", f"重试状态：第 {attempt} 次重试后签到成功"))
            return results
        if attempt < MAX_SIGNIN_RETRIES:
            log(f"账号 {index} 签到失败，5 秒后进行第 {attempt + 1} 次重试")
            time.sleep(5)

    results.append(Result("error", f"重试状态：已重试 {MAX_SIGNIN_RETRIES} 次，最终仍失败"))
    return results


def format_report(index, customer_code, results):
    lines = [f"### 账号 {index}（客编 {customer_code}）"]
    lines.extend(f"- {result.message}" for result in results)
    return "\n".join(lines)


def send_report(reports, failed):
    # 所有账号汇总后，仅通过一个 Server 酱 SendKey 推送一次。
    title = "jlc签到失败" if failed else "嘉立创签到汇总"
    response = requests.post(
        f"https://sctapi.ftqq.com/{SEND_KEY}.send",
        data={"text": title, "desp": "\n\n".join(reports)},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    log(f"通知发送完成，标题：{title}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not ACCOUNTS:
        log("请配置 ACCOUNTS")
        return

    reports = []
    failed = False
    for index, account in enumerate(ACCOUNTS, start=1):
        token = account["token"]
        customer_code = account["customer_code"]
        log(f"开始处理账号 {index}/{len(ACCOUNTS)}，客编 {customer_code}")
        results = sign_with_retries(token, index)
        report = format_report(index, customer_code, results)
        reports.append(report)
        # 推送内容同时写入标准输出，供 GitHub、任务计划和 systemd 日志查看。
        log(f"账号 {index} 签到结果：\n{report}")
        failed = failed or has_failure(results)

    if SEND_KEY:
        send_report(reports, failed)
    else:
        log("未配置 SEND_KEY，跳过微信推送")


if __name__ == "__main__":
    main()
