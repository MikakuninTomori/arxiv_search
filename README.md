# arxiv_search
arXivで論文を検索し、ChatGPTで要約後、Slackへ投稿するbotです。

## インストール
リポジトリのクローン後、envファイルに環境変数を設定してください。
その後、Dockerfileをビルドし、イメージをArtifact RegistryへPushします。
またはGoogle Cloud CLIでビルドでも構いません。以下を参照してください。
https://cloud.google.com/build/docs/running-builds/submit-build-via-cli-api?hl=ja
ビルド後、Code Runへデプロイを行います。
Cloud Scheduler で定期的にエンドポイントを呼び出すように設定します。Cloud Runで生成されたURLに /run を追加したエンドポイントを設定してください。
例: https://[GENERATED_CLOUD_RUN_URL]/run

# 仕様
呼び出されるたびにキーワードの中からランダムに３つ選択し、論文を探します。
cs(Computer Science).AIから探索し、見つからない場合はarXivのcsジャンルを全て探索します。必要なジャンルだけを追加してください。ジャンルに関しては以下を参考にしてください。

https://arxiv.org/category_taxonomy
GPTは3.5-turboを使用します。

## Slackコマンド
Slackで使用できるコマンドは次の通りです。
-	@bot_name nowlist : 現在のキーワードリストを表示します。
- @bot_name <キーワード> : 指定したキーワードを新たに追加します。

## 使用API
- arXiv API
- OpenAI API
- Slack API
