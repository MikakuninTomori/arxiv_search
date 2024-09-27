import os
import datetime as dt
import random
from typing import Set
import threading
import arxiv
import openai
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify

app = Flask(__name__)

load_dotenv()

# 各APIのキーとトークン
openai.api_key = os.getenv("OPENAI_API_KEY")
SLACK_API_TOKEN = os.getenv("SLACK_API_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# Slack appの初期化
slack_app = App(token=SLACK_API_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
handler = SlackRequestHandler(slack_app)

# Slackのチャンネル指定,クライアントの初期化
SLACK_CHANNEL = "channel name"
client = WebClient(token=SLACK_API_TOKEN)

# キーワードの初期値　
keyword_list = ["AI"]

# クエリのテンプレート
QUERY_TEMPLATE = "%28 ti:%22{}%22 OR abs:%22{}%22 %29 AND submittedDate: [{} TO {}]"

# Categories ここではcs(Computer Science)の全てを取得します
CATEGORIES = {
    "cs.AI", "cs.AR", "cs.CC", "cs.CE", "cs.CG", "cs.CL", "cs.CR", "cs.CV",
    "cs.CY", "cs.DB", "cs.DC", "cs.DL", "cs.DM", "cs.DS", "cs.ET", "cs.FL",
    "cs.GL", "cs.GR", "cs.GT", "cs.HC", "cs.IR", "cs.IT", "cs.LG", "cs.LO",
    "cs.MA", "cs.MM", "cs.MS", "cs.NA", "cs.NE", "cs.NI", "cs.OH", "cs.OS",
    "cs.PF", "cs.PL", "cs.RO", "cs.SC", "cs.SD", "cs.SE", "cs.SI", "cs.SY"
}

SYSTEM = """
### 指示 ###
論文の内容を理解した上で，重要なポイントを箇条書きで3点書いてください。

### 箇条書きの制約 ###
- 最大3個
- 必ず日本語
- 箇条書き1個を50文字以内
"""

def get_summary(result: arxiv.Result) -> str:
    text = f"title: {result.title}\nbody: {result.summary}"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": text}
            ],
            temperature=0.25
        )
        summary = response["choices"][0]["message"]["content"]
        title_en = result.title
        title, *body = summary.split("\n")
        body = "\n".join(body)
        date_str = result.published.strftime("%Y-%m-%d %H:%M:%S")
        message = f"発行日: {date_str}\n{result.entry_id}\n{title_en}\n{title}\n{body}\n"
        return message
    except Exception as e:
        return f"Error: {e}"
    

def process_arxiv_search(keyword: str, paper: Set[str]) -> Set[str]:
    # arXivの更新頻度を加味して今日から7日前の値をセット
    today = dt.datetime.today() - dt.timedelta(days=7)
    base_date = today - dt.timedelta(days=1)
    result_list = []
    # CATEGORIESの中のすべてのカテゴリで検索を行う
    for category in CATEGORIES:
        # カテゴリごとにクエリを作成
        # 今日から8日前から7日前の1日
        query = f"(ti:{keyword} OR abs:{keyword}) AND cat:{category} AND submittedDate:[{base_date.strftime('%Y%m%d')} TO {today.strftime('%Y%m%d')}]"
        
        # arxiv APIを使った検索
        search = arxiv.Search(
            query=query,
            max_results=1,  # 各カテゴリで最新の1件を取得　取得したい論文の数はこのパラメータを変更
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        
        # 検索結果を処理
        for result in search.results():
            if result.title in paper:
                continue
            # カテゴリに該当するものを追加
            result_list.append(result)
            paper.add(result.title)

        # 指定したキーワードで1つ結果が見つかった時点で検索を終了し,CATEGORIES内の他のカテゴリの検索を行わない
        # 全てのカテゴリーで検索を行いたい場合は以下のif文を消す,または条件を変える
        if len(result_list) >= 1:
            break
        

    # 結果がなかった場合はSlackにメッセージを送信
    if not result_list:
        client.chat_postMessage(channel=SLACK_CHANNEL, text=f"{'='*40}\nキーワード {keyword} に該当する論文が見つかりませんでした\n{'='*40}")
        return paper

    # 検索結果をSlackに投稿
    for result in result_list:
        try:
            message = f"{keyword}: \n" + get_summary(result)
            client.chat_postMessage(channel=SLACK_CHANNEL, text=message)
        except SlackApiError as e:
            print(f"Error posting message: {e}")

    return paper

def process_slack_event(text: str):
    if 'nowlist' in text.lower():
        keyword_list_str = '\n'.join(keyword_list)
        client.chat_postMessage(channel=SLACK_CHANNEL, text=f"現在のキーワードリスト:\n{keyword_list_str}")
    else:
        # メッセージの中からキーワードを抽出
        # textにはメンションごと入ってくるので,最初の単語(アプリ名)を消して再結合
        keyword = ' '.join(text.split()[1:])

        # 新しいキーワードをリストに追加
        keyword_list.append(keyword)

        # キーワードが追加されたことをSlackに返信
        client.chat_postMessage(channel=SLACK_CHANNEL, text=f"キーワード '{keyword}' をリストに追加しました。")

@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json
    event = data.get('event', {})

    # Slackのチャレンジリクエストに対応
    if data.get('type') == 'url_verification':
        return data['challenge'], 200, {'Content-Type': 'text/plain'}

    # メンションイベントかどうか確認
    if event.get('type') == 'app_mention':
        text = event.get('text', '')

        # threadingでイベントを処理
        threading.Thread(target=process_slack_event, args=(text,)).start()

    # 即座にHTTP 200レスポンスを返す
    return 'OK', 200

# 実行　
@app.route('/run', methods=['GET'])
def run_process_arxiv_search():
    paper = set()
    # ランダムで3つのキーワードを抽出して検索を行う
    random_keyword = random.sample(keyword_list, 3)
    for keyword in random_keyword:
        paper = process_arxiv_search(keyword, paper)
    return jsonify({'status': 'process_arxiv_search completed'}), 200

if __name__ == '__main__':
    port = 8080
    app.run(host='0.0.0.0', port=port)