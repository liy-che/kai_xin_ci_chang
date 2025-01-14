import argparse
import base64
import hashlib
import io
import json
import os
import zipfile

import pandas as pd
import requests

import os, os.path

HJ_APPKEY = "45fd17e02003d89bee7f046bb494de13"
LOGIN_URL = "https://pass.hujiang.com/Handler/UCenter.json?action=Login&isapp=true&language=zh_CN&password={password}&timezone=8&user_domain=hj&username={user_name}"
COVERT_URL = "https://pass-cdn.hjapi.com/v1.1/access_token/convert"
# type 1: current & used
# type 3: used
# type 4: current
MY_BOOKS_URL = (
    "https://cichang.hjapi.com/v3/user/me/book_study?type=3&start=0&limit=1000"
)
STUDY_BOOK_INFO_URL = "https://cichang.hjapi.com/v3/user/me/book_study/{book_id}"
STUDY_BOOK_RESOURCE_INFO_URL = (
    "https://cichang.hjapi.com/v3/user/me/book/{book_id}/resource"
)
TO_SAVE_FILES_DICT = {
    "sentAudioResource": "sentences",
    "wordAudioResource": "words",
    "textResource": "files",
}
FILES_ROOT = "FILES_OUT"
DEFAULT_WORD_FILE_ROOT = os.path.join(FILES_ROOT, "files", "word.txt")
DEFAULT_TO_CSV_NAME = "my_learning_book.csv"


def md5_encode(string):
    m = hashlib.md5()
    m.update(string.encode())
    return m.hexdigest()


def decode(s):
    try:
        bytes = bytearray(base64.b64decode(s))
        for i in range(len(bytes)):
            bytes[i] = 255 ^ bytes[i]
        s = bytes.decode("utf8")
    except:
        pass
    return s


def get_zip_password(version_str):
    b = [ord(i) for i in version_str]
    b = [i ^ -1 for i in b]
    return str(base64.b64encode(bytes(x % 256 for x in b)))[2:-1]


def get_learning_books_info(s):
    r = s.get(MY_BOOKS_URL)
    if not r.ok:
        raise Exception("Can not get books info from hujiang")
    return r.json()["data"]["result"]


def get_book_resource_info(s, book_id):
    r = s.get(STUDY_BOOK_RESOURCE_INFO_URL.format(book_id=book_id))
    if not r.ok:
        raise Exception("Can not get this book resource from hujiang")
    return r.json()["data"]


def download_zip_files(file_root_url, zip_pass, file_dir):
    r = requests.get(file_root_url)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(file_dir, pwd=bytes(zip_pass, "utf-8"))


def login(user_name, password):
    s = requests.Session()
    password_md5 = md5_encode(password)
    r = s.get(LOGIN_URL.format(user_name=user_name, password=password_md5))
    if not r.ok:
        raise Exception(f"Someting is wrong to login -- {r.text}")
    # print(r.json())
    club_auth_cookie = r.json()["Data"]["Cookie"]
    data = {"club_auth_cookie": club_auth_cookie}
    headers = {"hj_appkey": HJ_APPKEY, "Content-Type": "application/json"}
    # real login to get real token
    r = s.post(COVERT_URL, headers=headers, data=json.dumps(data))
    if not r.ok:
        raise Exception(f"Get real token failed -- {r.text}")
    access_token = r.json()["data"]["access_token"]
    headers["Access-Token"] = access_token
    s.headers = headers
    return s


def make_path(s, prefix=""):
    # Anki format: [sound:audio\words\4100495.mp3]
    return f'[sound:{prefix+str(s)}.mp3]'


def parse_to_pandas(file_root=DEFAULT_WORD_FILE_ROOT):
    with open(file_root) as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df = df[
        [
            "ItemID",
            "WordID",
            "Word",
            "WordDef",
            "SentenceID",
            "Sentence",
            "SentenceDef",
            "UnitID",
        ]
    ]

    df["WordAudio"] = df["WordID"].apply(make_path, prefix="audio\words\\")
    df["SentenceAudio"] = df["WordID"].apply(make_path)
    df["WordDef"] = df["WordDef"].apply(decode)
    df["Sentence"] = df["Sentence"].apply(decode)
    df["SentenceDef"] = df["SentenceDef"].apply(decode)
    return df


def print_current_titles(learning_books_info):
    titles = [book["book"]["name"] + ' ' + str(book["book"]["wordCount"]) for book in learning_books_info]
    titles.sort()

    for title in titles:
        print(title)


def main(user_name, password):
    s = login(user_name, password)
    learning_books_info = get_learning_books_info(s)

    if not learning_books_info:
        print("No learning book for now")

    # only get the first book, you can DIY here
    now_learning_book_id = learning_books_info[0]["book"]["id"]
    book_resource_data = get_book_resource_info(s, now_learning_book_id)

    print_current_titles(learning_books_info)

    return

    for k, v in book_resource_data.items():
        if k not in TO_SAVE_FILES_DICT:
            continue
        version = v.get("version")
        url = v.get("url")
        if not version:
            try:
                version = url.split("/")[-1].split(".")[0]
            except Exception as e:
                print(f"Get zip version failed with error {str(e)}")
                raise
        zip_pass = get_zip_password(str(version))

        # TODO for each book
        file_dir = os.path.join("FILES_OUT", TO_SAVE_FILES_DICT.get(k))
        if not os.path.exists(file_dir):
            os.mkdir(file_dir)
        try:
            print(f"Downloading {url} please wait")
            download_zip_files(url, zip_pass, file_dir)
        except Exception as e:
            print(str(e))
            pass

    df = parse_to_pandas()
    df.to_csv(DEFAULT_TO_CSV_NAME)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("user_name", help="hujiang_user_name")
    parser.add_argument("password", help="hujiang_password")
    options = parser.parse_args()
    main(options.user_name, options.password)
