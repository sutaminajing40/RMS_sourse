import datetime
import time
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import streamlit as st
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from bokeh.models.widgets import Div
import os




def main():
    sp = authorization()
    with st.form('送信フォーム'):
        URL,username,genre,tempo,energy = initial_display()
        submitted = st.form_submit_button("送信")
        

    if submitted:
        

        with st.spinner('プレイリスト取得中...'):
            playlist_items = url_to_items(sp,URL)
        with st.spinner('楽曲情報取得中...'):
            all_song_data,target_song_data = load_items(genre,playlist_items)
        with st.spinner('推薦中...(10分ほどかかる場合があります)'):
            recommendation_ids = recommender(all_song_data,target_song_data,tempo,energy)
        display_result(sp,recommendation_ids)
        create_playlist(sp,recommendation_ids,username)



class StreamlitCacheHandler(spotipy.cache_handler.CacheHandler):
    """
    A cache handler that stores the token info in the session framework
    provided by streamlit.
    """
    def __init__(self, session):
        self.session = session

    def get_cached_token(self):
        token_info = None
        try:
            token_info = self.session["token_info"]
        except KeyError:
            print("Token not found in the session")

        return token_info

    def save_token_to_cache(self, token_info):
        try:
            self.session["token_info"] = token_info
        except Exception as e:
            print("Error saving token to cache: " + str(e))


def authorization():
    scope = "playlist-modify-public"
    cache_handler = StreamlitCacheHandler(st.session_state)  # same as the FlaskSessionCacheHandler
    auth_manager = spotipy.oauth2.SpotifyOAuth(scope=scope,
                                                cache_handler=cache_handler,
                                                show_dialog=True)
    # if there is no cached token, open the sign in page
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        auth_url = auth_manager.get_authorize_url()  # log in url

        if st.button('Log in'):
            js = "window.open('{}')".format(auth_url)  # New tab or window
            #js = "window.location.href = '{}'".format(os.environ['SPOTIPY_REDIRECT_URI'])  # Current tab
            html = '<img src onerror="{}">'.format(js)
            div = Div(text=html)
            st.bokeh_chart(div) 
            sp = spotipy.Spotify(auth_manager=auth_manager)  
        while not sp:
            time.sleep(1)
        return sp


#初期表示
def initial_display():
    #タイトル表示
    st.title('音楽推薦システム')
    #Spotify Playlist の共有URLを入力
    URL = st.text_input('URLを入力(公開プレイリストのみ)',value='https://open.spotify.com/playlist/4ovXpa5zN9xoannaeP7OZF?si=rb5xpbtoQQeHZPeyiX97mw')
    username = st.text_input('ユーザーidを入力',value='nohoarito_yuzu_334129')
    #ユーザが選択した要素
    tempo = st.slider(label='テンポ',min_value=0,max_value=100,value=50)
    energy = st.slider(label = 'エネルギー',min_value=0,max_value=100,value=50)
    
    #ユーザが選択したジャンル
    genre = st.selectbox('ジャンルを選択',('全て選択','邦ロック','ボカロ','J-POP','女性アイドル'))

    return URL,username,genre,tempo,energy


#プレイリスト共有URLからtarget_playlist_itemsを作成する
def url_to_items(sp,URL):
    #共有URLからプレイリストidを抜き出す
    target1 = 'playlist/'
    target2 = '?'
    idx1 = URL.find(target1)
    idx2 = URL.find(target2)
    playlist_id = URL[idx1+9:idx2]

    #楽曲情報を格納するdataframe
    items_df = pd.DataFrame()

    #playlist_idからプレイリスト内の楽曲情報を取り出せる
    playlist_items = sp.playlist_items(playlist_id)['items']

    #playlist_itemsの各楽曲から解析情報を取り出す
    for track in playlist_items:
        result = sp.audio_features(track['track']['id'])
        result[0]['name'] = track['track']['name']
        item = pd.DataFrame(result[0].values(),index=result[0].keys()).T
        item = item.set_index('name')
        items_df = pd.concat([items_df,item])

    return items_df


def load_items(genre,playlist_items):
    #選択されたジャンルによって取得する曲を選択
    #all_song_data:ジャンルに対応した全ての楽曲のデータ
    if genre == '全て選択':
        all_song_data = pd.read_csv('csvfiles/Jpop/music_data.csv')
        all_song_data = pd.concat([all_song_data,pd.read_csv('csvfiles/vocaloid/music_data.csv'),
        pd.read_csv('csvfiles/Japanese_band/music_data.csv'),pd.read_csv('csvfiles/girls_idol/music_data.csv')])
    if genre == '邦ロック':
        all_song_data = pd.read_csv('csvfiles/Japanese_band/music_data.csv')
    if genre == 'ボカロ':
        all_song_data = pd.read_csv('csvfiles/vocaloid/music_data.csv')
    if genre == 'J-POP':
        all_song_data = pd.read_csv('csvfiles/Jpop/music_data.csv')
    if genre == '女性アイドル':
        all_song_data = pd.read_csv('csvfiles/girls_idol/music_data.csv')


    target_song_data = playlist_items
    #推薦の対象となる曲にnotice = 1をそれ以外にnotice = 0を
    all_song_data['notice'] = 0
    target_song_data['notice'] = 1
    #列名の整頓
    all_song_data = all_song_data.reindex(columns=['name','id','notice','danceability','energy',
    'loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo'])
    target_song_data = target_song_data.reindex(columns=['name','id','notice','danceability','energy',
    'loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo'])

    return all_song_data,target_song_data


def recommender(all_song_data,target_song_data,tempo,energy):
    recommendation_ids = []
    #全曲データにtargetデータの値を一曲ずつ入れて最近傍探索で一番近い曲を探す
    for index,song_data in target_song_data.iterrows():
        #合体したデータの格納先
        ori_song_data = pd.DataFrame()
        ori_song_data = all_song_data.append(song_data)
        ori_song_data.drop_duplicates(subset='id',keep='last',inplace=True)
        ori_song_data.drop_duplicates(subset='name',keep='last',inplace=True)
        #正規化
        minmax_sc = MinMaxScaler()
        X = ori_song_data.loc[:,'danceability':'tempo']
        X = minmax_sc.fit_transform(X)
        ori_song_data.loc[:,'danceability':'tempo'] = X

        #バイアス
        tempo_bias = tempo*-0.015+2
        energy_bias = energy*-0.015+2
        ori_song_data['tempo']*=tempo_bias
        ori_song_data['energy']*=energy_bias
        #最近傍探索で一番近いものを探す
        comparison_songs = ori_song_data[ori_song_data.notice == 0]
        target_song = ori_song_data[ori_song_data.notice == 1]
        np_target_song = target_song[['danceability','energy','loudness','speechiness','acousticness',
        'instrumentalness','liveness','valence','tempo']].values
        #距離
        dis = 9999
        for index1,comparison_song in comparison_songs.iterrows():
            np_comparison_song = comparison_song[['danceability','energy','loudness','speechiness','acousticness',
            'instrumentalness','liveness','valence','tempo']].values
            new_dis = np.linalg.norm(np_target_song-np_comparison_song)
            if new_dis < dis:
                dis = new_dis
                #一番近い曲のid
                id = comparison_song['id']
        #最近傍探索の結果のidをlistで
        recommendation_ids.append(id)

    return recommendation_ids


def create_playlist(sp,items,username):
    #プレイリスト名設定
    dt_now = str(datetime.datetime.now().strftime('%Y年%m月%d日 %H時%M分%S秒'))
    playlist_name = 'おすすめ'+dt_now

    id = sp.user_playlist_create(user=username,name=playlist_name)['id']
    sp.playlist_add_items(playlist_id=id,items = items)


def display_result(sp,ids):
    results = []
    song_datas = sp.tracks(ids)['tracks']
    for data in song_datas:
        results.append([data['name'],data['artists'][0]['name']])
    result = pd.DataFrame(
        results,
        columns=['曲名','アーティスト名']
    )
    st.dataframe(result)

if __name__ == '__main__':
    main()