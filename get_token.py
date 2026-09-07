import shutil
import tempfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


profile_dir = tempfile.mkdtemp(prefix="jlc-token-")
options = Options()
options.add_argument(f"--user-data-dir={profile_dir}")

driver = webdriver.Chrome(options=options)
driver.get("https://m.jlc.com")

input("请在打开的浏览器中登录嘉立创，登录完成后按回车读取 token：")
token = driver.execute_script("return localStorage.getItem('X-JLC-AccessToken')")

print(f"\nTOKEN_LIST={token}")

driver.quit()
shutil.rmtree(profile_dir)
