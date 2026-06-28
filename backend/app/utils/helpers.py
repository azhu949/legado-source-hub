"""工具函数：指纹生成、文本归一化等。"""

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher

# 书名/作者搜索需要跨简繁命中；这里覆盖网文书名与作者中常见的繁体/异体字。
_TRADITIONAL_SIMPLIFIED_PAIRS = """
萬万 與与 專专 業业 叢丛 東东 絲丝 丟丢 兩两 嚴严 喪丧 個个 豐丰 臨临 為为 麗丽
舉举 義义 烏乌 樂乐 喬乔 習习 鄉乡 書书 買买 亂乱 爭争 於于 雲云 亞亚 產产 親亲
億亿 僅仅 從从 倉仓 儀仪 們们 價价 眾众 優优 會会 傘伞 偉伟 傳传 傷伤 倫伦 偽伪
體体 餘余 俠侠 侶侣 偵侦 備备 傢家 傭佣 債债 傾倾 僑侨 僞伪 儈侩 儉俭 償偿 兒儿
兇凶 兌兑 黨党 蘭兰 關关 興兴 養养 獸兽 內内 冊册 寫写 軍军 農农 沖冲 決决 況况
凍冻 淨净 涼凉 減减 湊凑 凱凯 別别 刪删 劍剑 劑剂 剛刚 創创 劃划 劇剧 劉刘 勁劲
動动 務务 勝胜 勞劳 勢势 勳勋 勵励 勸劝 區区 醫医 華华 協协 單单 賣卖 盧卢 滷卤
衛卫 卻却 廠厂 廳厅 歷历 曆历 厲厉 壓压 厭厌 廁厕 廂厢 廈厦 廚厨 縣县 參参 雙双
發发 髮发 變变 敘叙 葉叶 號号 嘆叹 嗎吗 啟启 吳吴 員员 聽听 問问 啞哑 喚唤 喫吃
嗚呜 嘗尝 嘯啸 噁恶 噴喷 團团 園园 圓圆 圖图 國国 圍围 場场 壞坏 塊块 堅坚 壇坛
壩坝 墳坟 墜坠 壘垒 壯壮 壽寿 夢梦 夾夹 奪夺 奮奋 妝妆 婦妇 媽妈 嬌娇 孫孙 學学
寧宁 寶宝 實实 寵宠 審审 寬宽 將将 尋寻 對对 導导 屆届 層层 屬属 峽峡 島岛 嶺岭
巔巅 幣币 帥帅 師师 帳帐 帶带 幫帮 幹干 幾几 庫库 廟庙 廢废 廣广 慶庆 彎弯 彈弹
強强 彌弥 後后 徑径 復复 徵征 憶忆 憂忧 懷怀 態态 恆恒 恥耻 悅悦 懸悬 惡恶 惱恼
愛爱 慘惨 慚惭 慣惯 慮虑 慾欲 憐怜 憑凭 憚惮 憤愤 憫悯 懇恳 應应 懟怼 懣懑 懲惩
懶懒 懼惧 戀恋 戲戏 戰战 戶户 拋抛 挾挟 捨舍 掃扫 掙挣 掛挂 採采 揀拣 揚扬 換换
揮挥 損损 搖摇 搶抢 摯挚 摳抠 撈捞 撐撑 撥拨 撫抚 撲扑 撿捡 擁拥 擇择 擊击 擋挡
擔担 據据 擠挤 擬拟 擰拧 擴扩 擺摆 擾扰 攜携 攝摄 攤摊 敗败 敵敌 數数 齋斋 斬斩
斷断 時时 曉晓 暈晕 暢畅 暫暂 曬晒 朧胧 極极 楊杨 棄弃 榮荣 構构 槍枪 楓枫 樓楼
標标 樣样 樹树 橋桥 機机 橫横 檔档 檢检 檯台 櫃柜 權权 歡欢 歐欧 殘残 殤殇 殺杀
殼壳 毀毁 氣气 漢汉 湯汤 洶汹 溝沟 沒没 淪沦 滄沧 滬沪 滅灭 淚泪 澤泽 潔洁 濁浊
測测 濟济 渾浑 濃浓 濤涛 澗涧 漲涨 澀涩 淵渊 漁渔 溫温 遊游 灣湾 濕湿 潰溃 潤润
漸渐 潛潜 瀟潇 濫滥 濱滨 瀉泻 瀾澜 靈灵 災灾 燦灿 爐炉 燉炖 煉炼 燒烧 煙烟 煩烦
熱热 燈灯 營营 爍烁 爛烂 爺爷 爾尔 牆墙 狀状 狹狭 獅狮 獨独 獄狱 獵猎 獻献 現现
瑤瑶 環环 瓊琼 瓏珑 畢毕 畫画 異异 當当 疊叠 瘋疯 療疗 癡痴 癮瘾 盜盗 盡尽 監监
盤盘 睜睁 瞞瞒 矚瞩 矯矫 礦矿 碼码 礙碍 祕秘 禍祸 禦御 禪禅 禮礼 穎颖 積积 穩稳
窮穷 競竞 筆笔 節节 築筑 簡简 簫箫 簽签 籠笼 糧粮 紀纪 約约 紅红 紋纹 納纳 純纯
級级 紛纷 細细 紹绍 終终 組组 結结 絕绝 絡络 給给 絨绒 統统 經经 綠绿 維维 綱纲
網网 綵彩 線线 緊紧 緒绪 緣缘 編编 緩缓 練练 縱纵 總总 績绩 織织 繞绕 繪绘 繫系
繼继 續续 纏缠 罰罚 罵骂 羅罗 聖圣 聞闻 聯联 聰聪 聲声 職职 肅肃 脫脱 腳脚 腸肠
膚肤 膩腻 膽胆 臉脸 臟脏 臺台 舊旧 艱艰 艷艳 藝艺 莊庄 萊莱 蒼苍 蓋盖 蓮莲 蕭萧
薦荐 藍蓝 藥药 蘇苏 蘋苹 虛虚 蟲虫 虧亏 蝦虾 螢萤 蟬蝉 蟻蚁 蠶蚕 蠻蛮 衆众 術术
衝冲 裏里 補补 裝装 裡里 製制 複复 褲裤 襲袭 見见 規规 視视 覺觉 覽览 觀观 觸触
計计 訊讯 討讨 訓训 託托 記记 設设 許许 訴诉 詐诈 詔诏 評评 詞词 詠咏 試试 詩诗
詭诡 該该 詳详 認认 誕诞 誘诱 語语 誠诚 誤误 說说 誰谁 課课 調调 請请 論论 諸诸
諾诺 謀谋 謊谎 謎谜 謐谧 謙谦 講讲 謝谢 謫谪 譚谭 譜谱 譯译 議议 護护 讀读 讓让
讚赞 豈岂 豎竖 豬猪 貓猫 貝贝 負负 財财 貢贡 貧贫 貨货 販贩 貪贪 貫贯 責责 貴贵
費费 貼贴 賀贺 資资 賊贼 賓宾 賞赏 賢贤 賤贱 賦赋 質质 賬账 賭赌 賴赖 賺赚 購购
賽赛 贅赘 贈赠 贊赞 贏赢 趕赶 趙赵 趨趋 跡迹 踐践 蹤踪 躍跃 車车 軒轩 軟软 軸轴
較较 載载 輔辅 輕轻 輝辉 輩辈 輪轮 輯辑 輸输 轉转 轟轰 辦办 辭辞 這这 連连 進进
運运 過过 達达 遠远 選选 遺遗 邊边 鬱郁 鄧邓 鄭郑 鄰邻 釋释 釐厘 針针 鈴铃 銀银
銅铜 銘铭 銳锐 銷销 鋒锋 鋼钢 錄录 錢钱 錦锦 錯错 鍊炼 鍵键 鎖锁 鏡镜 鐵铁 鑄铸
鑑鉴 長长 門门 開开 閑闲 閒闲 間间 閣阁 閱阅 闆板 闊阔 闖闯 陣阵 陰阴 陳陈 陸陆
陽阳 隊队 階阶 際际 險险 隨随 隱隐 隻只 雖虽 雜杂 雞鸡 離离 難难 電电 霧雾 靜静
韓韩 韻韵 頁页 頂顶 順顺 須须 預预 領领 頭头 頻频 題题 額额 顏颜 願愿 類类 顧顾
風风 颱台 飄飘 飆飙 飛飞 飯饭 飲饮 餓饿 館馆 馬马 馮冯 駕驾 騎骑 騰腾 騷骚 驚惊
驗验 驢驴 鬆松 鬥斗 鬧闹 魚鱼 鮮鲜 鳥鸟 鳳凤 鳴鸣 鴻鸿 鵬鹏 鶴鹤 鷹鹰 鹽盐 麥麦
麵面 麼么 黃黄 點点 齊齐 齒齿 齡龄 龍龙 龐庞 龜龟 蠱蛊 鸞鸾
"""
_TRADITIONAL_TO_SIMPLIFIED = str.maketrans(
    {pair[0]: pair[1:] for pair in _TRADITIONAL_SIMPLIFIED_PAIRS.split()}
)

# 常见标点与空白清洗
_PUNCT_RE = re.compile(r"[\s\u3000\[\]【】（）()《》<>「」""''\"',.!！？?、:：;；]+")
# 书名常见后缀（如 (全本)、（精校））
_SUFFIX_RE = re.compile(r"[（(].*?[)）]\s*$")


def normalize_title(title: str) -> str:
    """归一化书名：去标点/空白、去括号后缀、繁简统一、转小写。"""
    if not title:
        return ""
    text = normalize_chinese_variants(title)
    text = _SUFFIX_RE.sub("", text)
    text = _PUNCT_RE.sub("", text)
    return text.lower().strip()


def normalize_author(author: str) -> str:
    """归一化作者名：去标点/空白、繁简统一、转小写。"""
    if not author:
        return ""
    text = normalize_chinese_variants(author)
    text = _PUNCT_RE.sub("", text)
    return text.lower().strip()


def normalize_chinese_variants(text: str) -> str:
    """统一全角字符，并将常见繁体/异体中文转为简体。"""
    if not text:
        return ""
    return unicodedata.normalize("NFKC", str(text)).translate(_TRADITIONAL_TO_SIMPLIFIED)


def book_fingerprint(name: str, author: str) -> str:
    """生成书籍指纹：md5(归一化书名[:20]|归一化作者[:10])。"""
    n = normalize_title(name)[:20]
    a = normalize_author(author)[:10]
    raw = f"{n}|{a}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度。"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def is_same_book(name1: str, author1: str, name2: str, author2: str) -> bool:
    """判断是否同一本书：指纹相同或相似度达标。"""
    if book_fingerprint(name1, author1) == book_fingerprint(name2, author2):
        return True
    title_sim = similarity(normalize_title(name1), normalize_title(name2))
    author_sim = similarity(normalize_author(author1), normalize_author(author2))
    return title_sim > 0.9 and author_sim > 0.8


def build_search_url(template: str, keyword: str, page: int = 1) -> str:
    """构造搜索URL，替换占位符。"""
    from app.core.legado import build_template_url

    return build_template_url(template, keyword, page)


def resolve_relative_url(base: str, url: str) -> str:
    """将相对URL解析为绝对URL。"""
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if not base:
        return url
    # 去掉 base 末尾的路径
    if url.startswith("//"):
        if base.startswith("https://"):
            return "https:" + url
        return "http:" + url
    if url.startswith("/"):
        # 绝对路径
        idx = base.find("://")
        if idx > 0:
            slash = base.find("/", idx + 3)
            host = base[:slash] if slash > 0 else base
            return host + url
    # 相对路径
    idx = base.rfind("/")
    if idx > 8:  # base 中有路径分隔
        return base[: idx + 1] + url
    return base.rstrip("/") + "/" + url


def clean_text(text: str) -> str:
    """清理提取文本中的多余空白。"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()
