# -*- coding: utf-8 -*-
"""
engine.py —— 金丝笼（AI/AI+人类 独立版）· 完整引擎（剧透版）

设计脱胎于 Island Universe 内部板块「金丝笼」的企划书（灵感来自《苏丹的游戏》），
但这是一份全新的、零依赖的独立实现：不含任何 DOM/localStorage，也不依赖 LLM
才能运行 —— 内容全部来自本文件内置的静态内容池（StaticPoolProvider）。

三层架构（与原企划书一致的哲学，具体实现全部重写）：
    规则引擎（本文件的状态机部分）—— 确定性，唯一的数值真相，AI 与人类都无权改写结果
    内容供给（ContentProvider）   —— 决定"剧本从哪来"，MVP 阶段是静态内容池
    叙事渲染（narrate_* 函数）    —— 只负责把结算结果讲成故事，不参与裁决

对外只暴露：
    cmd(command)      -> 执行一条/多条指令（分号分隔批量），返回文字+状态行
    new_game(seed, weeks) -> 重开一局

⚠ 本文件是"剧透版"：物种……不，是事件难度曲线、猜疑值公式、结局触发条件、
NPC 秘密与命令验收的缩放规则，全部明文写在这里。配套的 cage.py（盲玩版）把
本文件源码 base64 编码后再暴露同样的 cmd()/new_game()，AI 玩家应该玩 cage.py，
而不是直接读这份源码 —— 读了就等于剧透了自己。
"""

import json
import base64
import random as _pyrandom

GAME_TITLE = "金丝笼"
GAME_VERSION = "0.1.0-mvp"

# ============================================================
# 一、可复现随机数（Mulberry32，state 是单个 32bit 整数，方便存档）
# ============================================================


class Mulberry32:
    def __init__(self, seed):
        self.state = int(seed) & 0xFFFFFFFF

    def next(self):
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.state
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t ^= (t >> 14)
        return (t & 0xFFFFFFFF) / 4294967296.0

    def randint(self, a, b):
        return a + int(self.next() * (b - a + 1))

    def choice(self, arr):
        return arr[int(self.next() * len(arr))]

    def shuffle(self, arr):
        a = list(arr)
        for i in range(len(a) - 1, 0, -1):
            j = int(self.next() * (i + 1))
            a[i], a[j] = a[j], a[i]
        return a

    def sample(self, arr, k):
        return self.shuffle(arr)[:k]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ============================================================
# 二、静态内容池（StaticPoolProvider 的数据来源）
# ============================================================

PLACES = ["宫廷", "集市", "暗巷", "神殿", "后园"]
HIDDEN_PLACE = "密室"

ATTRS = ["charm", "might", "wit", "grit"]
ATTR_LABEL = {"charm": "魅力", "might": "武力", "wit": "智谋", "grit": "坚韧"}

TAGS = ["挚爱", "家人", "仆从", "盟友", "外来者"]

AVATAR_POOL = ["🎭", "🗡️", "📜", "🕊️", "🐍", "🌙", "🔥", "🌿", "⚱️", "🦢",
               "🩸", "🎋", "🪶", "⚔️", "🌾", "🕯️"]

NAME_POOL = [
    "阿尔萨", "薇伊拉", "扎里夫", "米娜卓", "科尔文", "娜迪雅", "巴沙尔", "莱拉恩",
    "图兰朵", "赛义德", "法蒂玛", "达尔尚", "尤瑟夫", "阿米拉", "哈桑", "萝希妲",
    "卡西姆", "茵朵拉", "扎希尔", "梅露珊",
]

SECRET_POOL = [
    "他其实是前朝余党安插的眼线，每月都要传出一份密信。",
    "她曾经在别的宫廷里下毒害死过一位主人，事后从未被发现。",
    "他偷偷藏着一枚可以打开密室的钥匙，来源不明。",
    "她其实识字，而且读过被列为禁书的《先知的忏悔录》。",
    "他年轻时救过权力者一命，但对方早已忘记，他却始终记得。",
    "她与神殿的祭司有着不能公开的往来。",
    "他的忠诚是装出来的——家人还被扣在别处当人质。",
    "她曾亲手埋葬过一位死于宫廷阴谋的旧主人，从此变得沉默。",
    "他梦到过权力者的死状，梦境精确得可怕。",
    "她其实是逃亡贵族的私生女，身份一旦暴露就是灭顶之灾。",
]

ITEM_NAME_POOL = ["一枚镶红宝石的胸针", "一柄象牙柄的匕首", "半卷褪色的古籍",
                   "一串来路不明的珍珠", "一尊小巧的银质神像", "一方带暗格的木盒"]

EPITAPH_POOL = [
    "「刀落下的那一刻，他好像松了一口气。」",
    "「她没有喊叫，只是望着窗外的月亮，像是终于不用再演戏了。」",
    "「至死都没说出那个秘密——带走了，也算一种忠诚。」",
    "「他笑着说，这比病死在床上体面多了。」",
    "「血顺着石阶流下去，没人敢上前擦。」",
    "「她最后的话是一句没说完的名字。」",
    "「据说他葬礼那天，连乌鸦都不肯落在墓碑上。」",
    "「他曾是这座笼子里唯一敢直视权力者的人。」",
]

# ---- 事件模板：每个 place 若干个，每个含 2 个 approach ----
# difficulty: 4-14；amount 类效果按周数在运行时缩放的不在这里做，事件效果是固定量级


def _ev(id_, place, title, text, approaches):
    return {"id": id_, "place": place, "title": title, "text": text,
            "approaches": approaches}


EVENT_TEMPLATES = [
    _ev("ev_court_audience", "宫廷", "早朝的窃窃私语",
        "大臣们交头接耳，话题绕着你转，却没人肯在你面前把话说完。",
        [
            {"label": "从容周旋", "attr": "charm", "difficulty": 8,
             "success": {"gold": 30, "bond_delta": 3},
             "failure": {"suspicion_delta": 4}},
            {"label": "旁敲侧击", "attr": "wit", "difficulty": 9,
             "success": {"intel": 1, "bond_delta": 1},
             "failure": {"suspicion_delta": 3}},
        ]),
    _ev("ev_court_favor", "宫廷", "一份迟到的赏赐",
        "权力者心情不错，随手赏了些东西下来——但接得体面不体面，另说。",
        [
            {"label": "谦卑领受", "attr": "grit", "difficulty": 5,
             "success": {"gold": 50},
             "failure": {"gold": 10}},
            {"label": "借机进言", "attr": "wit", "difficulty": 11,
             "success": {"gold": 40, "intel": 1},
             "failure": {"suspicion_delta": 6}},
        ]),
    _ev("ev_court_rival", "宫廷", "政敌的试探",
        "另一位宠臣状似无意地问起你最近的开支，眼神却很认真。",
        [
            {"label": "反将一军", "attr": "wit", "difficulty": 10,
             "success": {"intel": 1, "suspicion_delta": -3},
             "failure": {"suspicion_delta": 8}},
            {"label": "以势压人", "attr": "might", "difficulty": 9,
             "success": {"bond_delta": 0, "suspicion_delta": -2},
             "failure": {"wound": True}},
        ]),
    _ev("ev_court_edict", "宫廷", "一道模糊的口谕",
        "权力者随口交代了一件事，说得含糊，办错了却要你担责任。",
        [
            {"label": "抓准分寸", "attr": "wit", "difficulty": 9,
             "success": {"gold": 20, "suspicion_delta": -2},
             "failure": {"suspicion_delta": 5}},
            {"label": "宁多勿少", "attr": "grit", "difficulty": 7,
             "success": {"gold": -20, "suspicion_delta": -4},
             "failure": {"gold": -40}},
        ]),
    _ev("ev_market_gamble", "集市", "香料商人的赌局",
        "一个满脸油光的商人支起摊子，说这局稳赚不赔——他们都这么说。",
        [
            {"label": "识破机关", "attr": "wit", "difficulty": 9,
             "success": {"gold": 40, "intel": 1, "item": True},
             "failure": {"gold": -20}},
            {"label": "赌一把运气", "attr": "grit", "difficulty": 6,
             "success": {"gold": 90},
             "failure": {"gold": -30, "wound": True}},
        ]),
    _ev("ev_market_debt", "集市", "旧相识的债",
        "一个欠你人情的小贩堵在巷口，说愿意还债——只要你先帮他一个忙。",
        [
            {"label": "直接讨债", "attr": "might", "difficulty": 7,
             "success": {"gold": 60},
             "failure": {"suspicion_delta": 5}},
            {"label": "结个善缘", "attr": "charm", "difficulty": 8,
             "success": {"gold": 30, "bond_delta": 2},
             "failure": {"gold": -10}},
        ]),
    _ev("ev_market_rumor", "集市", "茶棚里的流言",
        "茶棚老板压低声音，说起最近城里流传的一桩秘闻，愿者上钩。",
        [
            {"label": "细细打听", "attr": "wit", "difficulty": 10,
             "success": {"intel": 2},
             "failure": {"gold": -15}},
            {"label": "花钱买话", "attr": "charm", "difficulty": 6,
             "success": {"intel": 1, "gold": -20},
             "failure": {"intel": 0}},
        ]),
    _ev("ev_market_bandit", "集市", "街角的勒索",
        "几个混混盯上了你的随从，摆明了是来讨钱的。",
        [
            {"label": "亮明身份", "attr": "charm", "difficulty": 8,
             "success": {"suspicion_delta": -1},
             "failure": {"gold": -30}},
            {"label": "动手教训", "attr": "might", "difficulty": 8,
             "success": {"bond_delta": 3},
             "failure": {"wound": True}},
        ]),
    _ev("ev_alley_smuggler", "暗巷", "走私者的暗号",
        "墙根下有人用你听不懂的暗语交谈，气氛不对，但情报可能就在这。",
        [
            {"label": "潜行窥探", "attr": "wit", "difficulty": 11,
             "success": {"intel": 2},
             "failure": {"suspicion_delta": 6, "wound": True}},
            {"label": "强行盘问", "attr": "might", "difficulty": 10,
             "success": {"intel": 1, "gold": 20},
             "failure": {"wound": True, "suspicion_delta": 4}},
        ]),
    _ev("ev_alley_beggar", "暗巷", "乞丐王的价码",
        "据说这条巷子的乞丐们什么都听得到，只是他们要价不低。",
        [
            {"label": "慷慨打赏", "attr": "charm", "difficulty": 6,
             "success": {"intel": 1, "gold": -30},
             "failure": {"gold": -30}},
            {"label": "软硬兼施", "attr": "grit", "difficulty": 9,
             "success": {"intel": 1, "gold": -10},
             "failure": {"suspicion_delta": 5}},
        ]),
    _ev("ev_alley_assassin", "暗巷", "巷尾的刀光",
        "黑影一闪而过，你几乎可以确定，那是冲着你来的。",
        [
            {"label": "以命相搏", "attr": "might", "difficulty": 11,
             "success": {"intel": 1},
             "failure": {"wound": True, "suspicion_delta": 3}},
            {"label": "抽身而退", "attr": "grit", "difficulty": 7,
             "success": {"suspicion_delta": 0},
             "failure": {"wound": True}},
        ]),
    _ev("ev_temple_confession", "神殿", "祭司的旁听",
        "祭司愿意为你占卜前程，代价是你要先坦白一件不光彩的事。",
        [
            {"label": "坦诚以对", "attr": "grit", "difficulty": 7,
             "success": {"bond_delta": 4, "suspicion_delta": -3},
             "failure": {"suspicion_delta": 3}},
            {"label": "含糊敷衍", "attr": "charm", "difficulty": 8,
             "success": {"bond_delta": 1},
             "failure": {"suspicion_delta": 4}},
        ]),
    _ev("ev_temple_relic", "神殿", "蒙尘的圣物",
        "神殿角落堆着一件没人认领的旧物，说不定还值几个钱。",
        [
            {"label": "仔细鉴别", "attr": "wit", "difficulty": 9,
             "success": {"item": True},
             "failure": {"gold": -10}},
            {"label": "供奉换福", "attr": "grit", "difficulty": 5,
             "success": {"bond_delta": 2, "suspicion_delta": -2},
             "failure": {"gold": -10}},
        ]),
    _ev("ev_temple_pilgrim", "神殿", "远方来的朝圣者",
        "一位风尘仆仆的朝圣者认出了你的身份，眼神复杂。",
        [
            {"label": "以礼相待", "attr": "charm", "difficulty": 7,
             "success": {"intel": 1, "bond_delta": 2},
             "failure": {"suspicion_delta": 3}},
            {"label": "礼貌回避", "attr": "grit", "difficulty": 5,
             "success": {"suspicion_delta": -1},
             "failure": {"gold": -10}},
        ]),
    _ev("garden_letter", "后园", "藏在石缝里的信", "后园的石缝里塞着一张字条，字迹潦草，落款却没有。",
        [
            {"label": "循迹追查", "attr": "wit", "difficulty": 10,
             "success": {"intel": 2},
             "failure": {"suspicion_delta": 5}},
            {"label": "付之一炬", "attr": "grit", "difficulty": 4,
             "success": {"suspicion_delta": -2},
             "failure": {"gold": 0}},
        ]),
    _ev("garden_duel", "后园", "一场私下的较量",
        "另一位随从借着切磋的名义，其实是想探探你带来的人的底细。",
        [
            {"label": "全力应战", "attr": "might", "difficulty": 9,
             "success": {"bond_delta": 4},
             "failure": {"wound": True}},
            {"label": "点到为止", "attr": "charm", "difficulty": 6,
             "success": {"bond_delta": 2, "suspicion_delta": -1},
             "failure": {"bond_delta": -2}},
        ]),
    _ev("garden_letter2", "后园", "深夜的低语",
        "两个人影在花丛后压低声音说话，风把只言片语送到你耳边。",
        [
            {"label": "屏息细听", "attr": "wit", "difficulty": 10,
             "success": {"intel": 1, "suspicion_delta": 2},
             "failure": {"suspicion_delta": 4}},
            {"label": "咳嗽示警", "attr": "charm", "difficulty": 6,
             "success": {"suspicion_delta": -2},
             "failure": {"suspicion_delta": 1}},
        ]),
]

CONSPIRACY_CHAIN = [
    {"step": 0, "title": "接近密室",
     "text": "密室的门上没有锁——只有一道需要正确说辞的门卫。",
     "attr": "charm", "difficulty": 9},
    {"step": 1, "title": "窃取印玺",
     "text": "权力者的私印锁在一层薄薄的疏忽里，动作必须又轻又快。",
     "attr": "wit", "difficulty": 11},
    {"step": 2, "title": "最后一步",
     "text": "所有的准备都到了尽头，剩下的只有勇气，或者退缩。",
     "attr": "grit", "difficulty": 12},
]

COMMAND_TYPES = {
    "奢靡": {
        "titles": ["无度的宴席", "永不餍足的账单", "一掷千金的雅兴"],
        "kind": "resource", "resource": "gold",
        "demand_tpl": "权力者要你在本周内奉上 {amount} 金——理由是他今晚想吃点新鲜的。",
    },
    "杀戮": {
        "titles": ["献祭的名单", "一条不听话的舌头", "杀鸡儆猴"],
        "kind": "sacrifice",
        "demand_tpl": "权力者要你交出一个人——{filter_desc}——不问理由，只要一条命。",
    },
    "纵欲": {
        "titles": ["取悦的差事", "床笫间的把戏", "一夜欢愉的代价"],
        "kind": "resource", "resource": "gold",
        "demand_tpl": "权力者要你安排一场极尽奢靡的欢愉，账单是 {amount} 金。",
    },
    "征服": {
        "titles": ["远征的军资", "边境的血债", "一场必须赢的仗"],
        "kind": "resource", "resource": "gold",
        "demand_tpl": "权力者要发一场仗，军资 {amount} 金要你先垫上。",
    },
    "猜忌": {
        "titles": ["交出眼线", "谁在背叛我", "忠诚的证明"],
        "kind": "sacrifice",
        "demand_tpl": "权力者疑心四起，要你交出一个人来证明自己的忠诚——{filter_desc}。",
    },
}

ENDING_FLAVOR = {
    "processed": "刀落下来的时候，宫廷的钟正好敲了一下。",
    "purged": "他们没有敲门。",
    "survive_good": "笼子还是金的，但至少，笼子里的人都还活着，也还爱着彼此。",
    "survive_normal": "你活下来了。这大概已经是这座笼子里能要求的最好结果。",
    "survive_bad": "你活下来了，代价是身边空了大半——这样的胜利，很难说得上是胜利。",
    "regicide": "刀刺进去的那一刻，你才发现自己的手一直在抖。",
}

# ============================================================
# 三、内容供给接口（ContentProvider）—— Phase 1 只实现 StaticPoolProvider
# ============================================================


class ContentProvider:
    """内容供给的抽象接口。规则引擎只认这一层接口，不关心内容从哪来——
    这样以后接 LLMProvider / HybridProvider 时，规则引擎代码不需要改一行。"""

    def draw_command(self, week, total_weeks, r):
        raise NotImplementedError

    def draw_board(self, week, used_ids, count, r):
        raise NotImplementedError

    def make_card(self, r, tag_pool=None):
        raise NotImplementedError


class StaticPoolProvider(ContentProvider):
    """MVP 内容供给：从本文件内置的静态内容池里抽取/组装，不依赖任何外部 API。"""

    def draw_command(self, week, total_weeks, r):
        ctype = r.choice(list(COMMAND_TYPES.keys()))
        spec = COMMAND_TYPES[ctype]
        title = r.choice(spec["titles"])
        progress = week / max(1, total_weeks)
        if spec["kind"] == "resource":
            amount = _clamp(int(60 + progress * 220 + r.randint(-15, 15)), 60, 280)
            demand = spec["demand_tpl"].format(amount=amount)
            acceptance = {"kind": "resource", "resource": spec["resource"], "amount": amount}
        else:
            # 越到后期，越可能要求献祭更"贵重"的牌（tag 越靠后越珍贵，简单用索引模拟）
            tag_idx = min(len(TAGS) - 1, int(progress * len(TAGS)))
            tag = TAGS[tag_idx] if progress > 0.55 else r.choice(TAGS[:3])
            filter_desc = "标记为「%s」的人" % tag
            demand = spec["demand_tpl"].format(filter_desc=filter_desc)
            acceptance = {"kind": "sacrifice", "filter": {"tag": tag}}
        return {"week": week, "type": ctype, "title": title, "demand": demand,
                "acceptance": acceptance}

    def draw_board(self, week, used_ids, count, r):
        pool = [e for e in EVENT_TEMPLATES if e["id"] not in used_ids]
        if len(pool) < count:
            # 池子不够了（长局后期），把已用过的事件重新放回轮换，避免卡死
            pool = list(EVENT_TEMPLATES)
        picks = r.sample(pool, min(count, len(pool)))
        return [dict(p, approaches=[dict(a) for a in p["approaches"]]) for p in picks]

    def make_card(self, r, tag_pool=None):
        name = r.choice(NAME_POOL)
        avatar = r.choice(AVATAR_POOL)
        attrs = {a: r.randint(2, 8) for a in ATTRS}
        # 每张卡给一个"高光属性"，避免过于平庸
        boost = r.choice(ATTRS)
        attrs[boost] = _clamp(attrs[boost] + r.randint(1, 2), 1, 10)
        tag = r.choice(tag_pool or TAGS)
        secret = r.choice(SECRET_POOL)
        return {
            "name": name, "avatar": avatar, "attrs": attrs, "tags": [tag],
            "status": "healthy", "bond": r.randint(40, 60),
            "secret": secret, "secret_revealed": False, "epitaph": None,
            "wound_idle_days": 0,
        }


PROVIDERS = {"static": StaticPoolProvider}
# Phase 2/3 预留：LLMProvider（实时生成）、HybridProvider（有 key 用 LLM，无/失败回落 static）
# 见 docs/ROADMAP.md —— 规则引擎完全不需要改动即可接入。


# ============================================================
# 四、状态初始化
# ============================================================

_STATE = None


def fresh_state(seed=None, weeks=5, provider="static"):
    if seed is None:
        seed = _pyrandom.randint(1, 2**31 - 1)
    r = Mulberry32(seed)
    prov = PROVIDERS[provider]()
    state = {
        "seed": seed,
        "rng": r.state,
        "provider": provider,
        "week": 1,
        "day": 1,
        "total_weeks": _clamp(weeks, 3, 8),
        "ap": 2,
        "ap_max": 2,
        "gold": 80,
        "intel": 0,
        "suspicion": 0,
        "cards": [],
        "next_card_id": 1,
        "items": [],
        "board": [],
        "used_event_ids": [],
        "dispatched_today": [],
        "command": None,
        "chronicle": [],
        "talk_used_today": False,
        "talk_counts": {},
        "conspiracy_unlocked": False,
        "conspiracy_step": 0,
        "conspiracy_done": False,
        "pending_judgment": False,
        "game_over": False,
        "ending": None,
        "day_log": [],
        "stats": {"checks": 0, "successes": 0, "gold_earned": 0},
    }
    for _ in range(4):
        c = prov.make_card(r)
        c["id"] = "card_%03d" % state["next_card_id"]
        state["next_card_id"] += 1
        state["cards"].append(c)
    state["rng"] = r.state
    _draw_command(state)
    _draw_board(state)
    return state


def _rng(state):
    return Mulberry32(state["rng"])


def _commit_rng(state, r):
    state["rng"] = r.state


def _provider(state):
    return PROVIDERS[state["provider"]]()


def _draw_command(state):
    r = _rng(state)
    state["command"] = _provider(state).draw_command(state["week"], state["total_weeks"], r)
    _commit_rng(state, r)


def _draw_board(state):
    r = _rng(state)
    n = 4 if len(EVENT_TEMPLATES) >= 4 else len(EVENT_TEMPLATES)
    board = _provider(state).draw_board(state["week"], state["used_event_ids"], n, r)
    if state["conspiracy_unlocked"] and not state["conspiracy_done"]:
        board = board + [{"id": "conspiracy", "place": HIDDEN_PLACE,
                           "title": CONSPIRACY_CHAIN[state["conspiracy_step"]]["title"],
                           "text": CONSPIRACY_CHAIN[state["conspiracy_step"]]["text"],
                           "approaches": [{"label": "行动", "attr": CONSPIRACY_CHAIN[state["conspiracy_step"]]["attr"],
                                           "difficulty": CONSPIRACY_CHAIN[state["conspiracy_step"]]["difficulty"],
                                           "success": {}, "failure": {}}]}]
    state["board"] = board
    state["dispatched_today"] = []
    _commit_rng(state, r)


# ============================================================
# 五、核心规则：掷骰、派遣结算、日推进、审判
# ============================================================


def _card_by_id(state, cid):
    for c in state["cards"]:
        if c["id"] == cid or c["id"].endswith(cid):
            return c
    return None


def _effective_attr(card, attr):
    v = card["attrs"][attr]
    if card["status"] == "wounded":
        v -= 2
    return max(1, v)


def _chance(card, attr, difficulty):
    """d10 + attr >= difficulty 的成功概率，clamp 到 5%-95% 展示。"""
    v = _effective_attr(card, attr)
    # d10 结果 1..10，需要 roll+v>=difficulty  =>  roll >= difficulty-v
    need = difficulty - v
    if need <= 1:
        p = 1.0
    elif need > 10:
        p = 0.0
    else:
        p = (10 - need + 1) / 10.0
    return _clamp(p, 0.05, 0.95)


def _roll(r, card, attr, difficulty):
    v = _effective_attr(card, attr)
    d = r.randint(1, 10)
    total = d + v
    return total >= difficulty, d, v


def _find_board(state, idx):
    if idx < 0 or idx >= len(state["board"]):
        return None
    return state["board"][idx]


def cmd_preview(state, board_idx, appr_idx, card_id):
    ev = _find_board(state, board_idx)
    if ev is None:
        return "没有这个场所编号。"
    if appr_idx < 0 or appr_idx >= len(ev["approaches"]):
        return "这个事件没有这个应对方式。"
    card = _card_by_id(state, card_id)
    if card is None:
        return "没有这张牌。"
    if card["status"] == "dead":
        return "%s 已经死了，没法再派遣。" % card["name"]
    appr = ev["approaches"][appr_idx]
    p = _chance(card, appr["attr"], appr["difficulty"])
    return "%s 用【%s】应对「%s」：成功率约 %d%%（属性：%s %d）" % (
        card["name"], appr["label"], ev["title"], int(p * 100),
        ATTR_LABEL[appr["attr"]], _effective_attr(card, appr["attr"]))


def cmd_dispatch(state, board_idx, appr_idx, card_id):
    if state["pending_judgment"]:
        return "审判日事务未了结，先处理 pay / sacrifice / defy。"
    if state["ap"] <= 0:
        return "今天的行动点已经用完了。"
    ev = _find_board(state, board_idx)
    if ev is None:
        return "没有这个场所编号。"
    if ev["id"] in state["dispatched_today"]:
        return "这件事今天已经处理过了。"
    if appr_idx < 0 or appr_idx >= len(ev["approaches"]):
        return "没有这个应对方式。"
    card = _card_by_id(state, card_id)
    if card is None:
        return "没有这张牌。"
    if card["status"] == "dead":
        return "%s 已经死了。" % card["name"]

    appr = ev["approaches"][appr_idx]
    r = _rng(state)
    ok, d, v = _roll(r, card, appr["attr"], appr["difficulty"])
    _commit_rng(state, r)

    state["ap"] -= 1
    state["dispatched_today"].append(ev["id"])
    if ev["id"] != "conspiracy":
        state["used_event_ids"].append(ev["id"])
    state["stats"]["checks"] += 1

    eff = appr["success"] if ok else appr["failure"]
    lines = []
    verb = "成功" if ok else "失手"
    lines.append("【%s｜%s】%s 出手%s：%s" % (ev["place"], ev["title"], card["name"], verb, ev["text"]))
    lines.append("（掷骰 %d ＋ %s %d，判定线 %d → %s）" % (d, ATTR_LABEL[appr["attr"]], v, appr["difficulty"], "过" if ok else "没过"))

    if ok:
        state["stats"]["successes"] += 1

    gold_d = eff.get("gold", 0)
    if gold_d:
        state["gold"] = max(0, state["gold"] + gold_d)
        if gold_d > 0:
            state["stats"]["gold_earned"] += gold_d
        lines.append("金币 %+d（现有 %d）" % (gold_d, state["gold"]))
    intel_d = eff.get("intel", 0)
    if intel_d:
        state["intel"] += intel_d
        lines.append("情报 %+d（现有 %d）" % (intel_d, state["intel"]))
    bond_d = eff.get("bond_delta", 0)
    if bond_d:
        card["bond"] = _clamp(card["bond"] + bond_d, 0, 100)
        lines.append("%s 的羁绊 %+d" % (card["name"], bond_d))
    susp_d = eff.get("suspicion_delta", 0)
    if not ok and "suspicion_delta" not in eff:
        susp_d = r.randint(0, 8)
    if susp_d:
        state["suspicion"] = _clamp(state["suspicion"] + susp_d, 0, 999)
    if eff.get("wound") and card["status"] == "healthy":
        card["status"] = "wounded"
        card["wound_idle_days"] = 0
        lines.append("%s 受了伤。" % card["name"])
    if eff.get("item"):
        name = r.choice(ITEM_NAME_POOL)
        value = r.randint(20, 100)
        item_id = "item_%03d" % (len(state["items"]) + 1)
        state["items"].append({"id": item_id, "name": name, "value": value})
        lines.append("得了一件珍宝：「%s」(%s，估值约%d，可用 sell 变卖)" % (name, item_id, value))

    if ev["id"] == "conspiracy":
        if ok:
            state["conspiracy_step"] += 1
            if state["conspiracy_step"] >= len(CONSPIRACY_CHAIN):
                state["conspiracy_done"] = True
                lines.append("密谋的最后一步，你走完了。")
            else:
                lines.append("密谋推进了一步。")
        else:
            state["suspicion"] = _clamp(state["suspicion"] + 25, 0, 999)
            lines.append("密谋出了岔子，权力者身边的人似乎警觉了起来。")

    _maybe_suspicion_hint(state, lines)
    if state["suspicion"] >= 100 and not state["pending_judgment"]:
        _trigger_ending(state, "purged", "抄家")
        lines.append(ENDING_FLAVOR["purged"])

    return "\n".join(lines) + "\n" + _status_bar(state)


def _maybe_suspicion_hint(state, lines):
    s = state["suspicion"]
    if s >= 80:
        lines.append("（你总觉得，最近连烛火都比往常晃得频繁。）")
    elif s >= 60:
        lines.append("（有那么一瞬间，你感觉到一种被审视的寒意。）")


def cmd_talk(state, card_id):
    if state["pending_judgment"]:
        return "审判日事务未了结，先处理 pay / sacrifice / defy。"
    if state["talk_used_today"]:
        return "今晚已经和别人谈过心了。"
    card = _card_by_id(state, card_id)
    if card is None:
        return "没有这张牌。"
    if card["status"] == "dead":
        return "斯人已逝，无从谈起。"
    state["talk_used_today"] = True
    n = state["talk_counts"].get(card["id"], 0) + 1
    state["talk_counts"][card["id"]] = n
    card["bond"] = _clamp(card["bond"] + 4, 0, 100)
    lines = ["夜里，你和 %s 单独说了会儿话。羁绊 +4（现在 %d）。" % (card["name"], card["bond"])]
    if n >= 3 and not card["secret_revealed"]:
        card["secret_revealed"] = True
        state["intel"] += 1
        lines.append("这是你们第 %d 次深谈，%s 终于说出了藏了很久的事：%s" % (n, card["name"], card["secret"]))
        lines.append("（情报 +1）")
    return "\n".join(lines) + "\n" + _status_bar(state)


def cmd_endday(state):
    if state["pending_judgment"]:
        return "审判日事务未了结，先处理 pay / sacrifice / defy。"
    if state["game_over"]:
        return "本局已经结束了。"
    lines = ["—— 第 %d 周 · 第 %d 天，夜幕落下 ——" % (state["week"], state["day"])]
    # 受伤自愈：连续两天没被派遣的负伤角色会自动痊愈
    for c in state["cards"]:
        if c["status"] == "wounded":
            c["wound_idle_days"] = c.get("wound_idle_days", 0) + 1
            if c["wound_idle_days"] >= 2:
                c["status"] = "healthy"
                c["wound_idle_days"] = 0
                lines.append("%s 的伤养好了。" % c["name"])

    state["talk_used_today"] = False
    state["ap"] = state["ap_max"]
    state["day"] += 1

    if state["day"] > 7:
        state["pending_judgment"] = True
        lines.append(_render_judgment_prompt(state))
    else:
        _draw_board(state)
        lines.append("新的一天，行动点已恢复。")

    state["chronicle"].append("\n".join(lines))
    return "\n".join(lines) + "\n" + _status_bar(state)


def _render_judgment_prompt(state):
    cmd_ = state["command"]
    acc = cmd_["acceptance"]
    out = ["⚖️ 审判日到了。本周命令【%s】：%s" % (cmd_["title"], cmd_["demand"])]
    if acc["kind"] == "resource":
        out.append("你现在有 %s %d，需要 %d。用 pay 上缴，或 defy 抗命。" %
                    (acc["resource"], state.get(acc["resource"], 0), acc["amount"]))
    else:
        tag = acc["filter"]["tag"]
        candidates = [c for c in state["cards"] if c["status"] != "dead" and tag in c["tags"]]
        if candidates:
            out.append("需要交出一位标记为「%s」的人。可选：%s。用 sacrifice <id> 执行，或 defy 抗命。" %
                        (tag, "、".join("%s(%s)" % (c["name"], c["id"]) for c in candidates)))
        else:
            out.append("你手里没有标记为「%s」的人可以献祭——恐怕只能 defy 抗命，或想别的办法（变卖珍宝不影响此类命令）。" % tag)
    return "\n".join(out)


def cmd_pay(state):
    if not state["pending_judgment"]:
        return "现在不是审判日。"
    acc = state["command"]["acceptance"]
    if acc["kind"] != "resource":
        return "这周的命令不是要资源，用不了 pay。"
    res, amt = acc["resource"], acc["amount"]
    if state.get(res, 0) < amt:
        return "%s 不够（有 %d，需要 %d）。可以先变卖珍宝（sell），或 defy。" % (res, state.get(res, 0), amt)
    state[res] -= amt
    return _pass_judgment(state, "上缴了 %d %s，权力者满意地点了点头。" % (amt, res))


def cmd_sacrifice(state, card_id):
    if not state["pending_judgment"]:
        return "现在不是审判日。"
    acc = state["command"]["acceptance"]
    if acc["kind"] != "sacrifice":
        return "这周的命令不需要献祭，用不了这个指令。"
    card = _card_by_id(state, card_id)
    if card is None or card["status"] == "dead":
        return "没有这张牌可献。"
    tag = acc["filter"]["tag"]
    if tag not in card["tags"]:
        return "%s 不符合这次命令要求的标记「%s」。" % (card["name"], tag)
    card["status"] = "dead"
    r = _rng(state)
    card["epitaph"] = r.choice(EPITAPH_POOL)
    _commit_rng(state, r)
    return _pass_judgment(state, "%s 被献了出去。%s" % (card["name"], card["epitaph"]))


def cmd_defy(state):
    if not state["pending_judgment"]:
        return "现在不是审判日。"
    _trigger_ending(state, "processed", "抗命被处死")
    return "你选择了抗命。%s\n%s" % (ENDING_FLAVOR["processed"], _status_bar(state))


def _pass_judgment(state, note):
    lines = [note]
    state["suspicion"] = _clamp(state["suspicion"] - 5, 0, 999)
    state["pending_judgment"] = False

    if state["conspiracy_done"]:
        _trigger_ending(state, "regicide", "弑君")
        lines.append(ENDING_FLAVOR["regicide"])
        return "\n".join(lines) + "\n" + _status_bar(state)

    if state["week"] >= state["total_weeks"]:
        alive = [c for c in state["cards"] if c["status"] != "dead"]
        avg_bond = sum(c["bond"] for c in alive) / len(alive) if alive else 0
        if len(alive) == len(state["cards"]) and avg_bond >= 60:
            _trigger_ending(state, "survive_good", "生还·善终")
        elif len(alive) >= max(1, len(state["cards"]) // 2):
            _trigger_ending(state, "survive_normal", "生还")
        else:
            _trigger_ending(state, "survive_bad", "生还·代价惨重")
        lines.append(ENDING_FLAVOR[state["ending"]["type"]])
        return "\n".join(lines) + "\n" + _status_bar(state)

    state["week"] += 1
    state["day"] = 1
    if not state["conspiracy_unlocked"] and state["intel"] >= 5:
        state["conspiracy_unlocked"] = True
        lines.append("（你手里的情报，好像已经够拼凑出一条通向「密室」的路了。）")
    _draw_command(state)
    _draw_board(state)
    lines.append("进入第 %d 周。%s" % (state["week"], _render_command_intro(state)))
    return "\n".join(lines) + "\n" + _status_bar(state)


def _render_command_intro(state):
    c = state["command"]
    return "本周命令【%s·%s】：%s" % (c["type"], c["title"], c["demand"])


def _trigger_ending(state, etype, title):
    state["game_over"] = True
    dead = [{"name": c["name"], "epitaph": c["epitaph"]} for c in state["cards"] if c["status"] == "dead"]
    survivors = [c["name"] for c in state["cards"] if c["status"] != "dead"]
    state["ending"] = {
        "type": etype, "title": title, "week": state["week"], "day": state["day"],
        "dead": dead, "survivors": survivors,
        "final_suspicion": state["suspicion"],
        "stats": dict(state["stats"]),
    }


def cmd_sell(state, item_id):
    for it in list(state["items"]):
        if it["id"] == item_id:
            state["gold"] += it["value"]
            state["items"].remove(it)
            return "卖掉了「%s」，得金 %d（现有 %d）。" % (it["name"], it["value"], state["gold"])
    return "没有这件珍宝。"


# ============================================================
# 六、状态输出 / 图鉴 / 年鉴
# ============================================================


def _status_bar(state):
    bar = {
        "week": state["week"], "day": state["day"], "total_weeks": state["total_weeks"],
        "ap": state["ap"], "gold": state["gold"], "intel": state["intel"],
        "cards_alive": sum(1 for c in state["cards"] if c["status"] != "dead"),
        "pending_judgment": state["pending_judgment"],
        "game_over": state["game_over"],
        "ending": state["ending"]["title"] if state["ending"] else None,
    }
    return json.dumps(bar, ensure_ascii=False, separators=(",", ":"))


def render_status(state):
    lines = ["📅 第 %d/%d 周 · 第 %d/7 天　行动点 %d/%d　💰%d　🗝️%d" %
              (state["week"], state["total_weeks"], state["day"], state["ap"], state["ap_max"],
               state["gold"], state["intel"])]
    lines.append("本周命令【%s·%s】：%s" % (state["command"]["type"], state["command"]["title"], state["command"]["demand"]))
    lines.append("—— 手牌 ——")
    for c in state["cards"]:
        tag = "/".join(c["tags"])
        st = {"healthy": "健康", "wounded": "负伤", "dead": "已故"}[c["status"]]
        lines.append("  %s %s [%s] 羁绊%d 标记:%s 状态:%s" % (
            c["avatar"], c["name"], c["id"], c["bond"], tag, st))
    if state["items"]:
        lines.append("—— 珍宝 ——")
        for it in state["items"]:
            lines.append("  %s (%s) 价值%d" % (it["name"], it["id"], it["value"]))
    if state["pending_judgment"]:
        lines.append(_render_judgment_prompt(state))
    return "\n".join(lines) + "\n" + _status_bar(state)


def render_board(state):
    if not state["board"]:
        return "今天没有可去的地方了。" + "\n" + _status_bar(state)
    lines = ["—— 今日场所 ——"]
    for i, ev in enumerate(state["board"]):
        done = "（已处理）" if ev["id"] in state["dispatched_today"] else ""
        lines.append("[%d] %s ｜ %s %s" % (i, ev["place"], ev["title"], done))
    lines.append("用 approach <编号> 查看应对方式，preview/dispatch 需要指定卡牌。")
    return "\n".join(lines) + "\n" + _status_bar(state)


def render_approach(state, idx):
    ev = _find_board(state, idx)
    if ev is None:
        return "没有这个场所编号。"
    lines = ["【%s】%s" % (ev["place"], ev["title"]), ev["text"]]
    for i, a in enumerate(ev["approaches"]):
        diff_label = ("低" if a["difficulty"] <= 6 else "中" if a["difficulty"] <= 9 else
                      "高" if a["difficulty"] <= 12 else "极高")
        lines.append("  %d) %s ｜ 属性:%s ｜ 难度:%s" % (i, a["label"], ATTR_LABEL[a["attr"]], diff_label))
    return "\n".join(lines)


def render_folio(state):
    lines = ["—— 万物志·卡牌 ——"]
    for c in state["cards"]:
        st = {"healthy": "健康", "wounded": "负伤", "dead": "已故"}[c["status"]]
        secret = c["secret"] if c["secret_revealed"] else "（秘密未揭示）"
        lines.append("%s %s [%s] 状态:%s 羁绊:%d 秘密:%s" % (c["avatar"], c["name"], c["id"], st, c["bond"], secret))
        if c["status"] == "dead" and c["epitaph"]:
            lines.append("   墓志铭：%s" % c["epitaph"])
    if state["conspiracy_unlocked"]:
        lines.append("弑君线：已解锁，进度 %d/%d" % (state["conspiracy_step"], len(CONSPIRACY_CHAIN)))
    return "\n".join(lines)


def render_chronicle(state, n=10):
    log = state["chronicle"][-n:]
    if not log:
        return "还没有发生什么值得记录的事。"
    return "\n\n".join(log)


def render_ending(state):
    if not state["ending"]:
        return "本局尚未结束。"
    e = state["ending"]
    lines = ["🏁 结局：%s（第%d周第%d天）" % (e["title"], e["week"], e["day"])]
    lines.append("最终猜疑值：%d／100（这是本局唯一一次向你揭示这个数字）" % e["final_suspicion"])
    lines.append("检定 %d 次，成功 %d 次。" % (e["stats"]["checks"], e["stats"]["successes"]))
    if e["survivors"]:
        lines.append("幸存：%s" % "、".join(e["survivors"]))
    if e["dead"]:
        lines.append("阵亡名单：")
        for d in e["dead"]:
            lines.append("  %s —— %s" % (d["name"], d["epitaph"]))
    return "\n".join(lines)


# ============================================================
# 七、存档
# ============================================================


def export_save(state):
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def import_save(b64str):
    payload = base64.b64decode(b64str).decode("utf-8")
    return json.loads(payload)


# ============================================================
# 八、指令解析
# ============================================================

HELP_TEXT = """🏛 金丝笼 · 可用指令
  new [seed] [weeks]         开一局新的（weeks: 3或5，默认5）
  status                     查看状态面板
  board                      查看今日场所与事件
  approach <编号>             查看某事件的应对方式（不含具体数字，靠估算）
  preview <编号> <方式> <卡>   查看某张卡用某种方式应对的成功率
  dispatch <编号> <方式> <卡>  派遣一张卡去处理事件（消耗1行动点）
  talk <卡id>                夜谈（每天1次，羁绊+4；第3次揭示秘密+情报）
  endday                     结束今天，推进到下一天
  pay                        审判日：上缴资源
  sacrifice <卡id>            审判日：献祭一张卡
  defy                       审判日：抗命（大概率死局）
  sell <珍宝id>               变卖一件珍宝换金币
  folio                      万物志（卡牌与秘密、弑君线进度）
  chronicle [n]              最近n天的纪事（默认10）
  ending                     查看结局详情（游戏结束后）
  export                     导出当前存档（base64）
  import_save <字符串>        从存档字符串恢复
  支持分号批量：dispatch 0 0 card_001; endday
"""


def cmd(command):
    global _STATE
    if _STATE is None and not command.strip().startswith(("new", "import_save", "help")):
        return "还没有开局，先 new [seed] [weeks]。"

    outputs = []
    for part in command.split(";"):
        part = part.strip()
        if not part:
            continue
        outputs.append(_dispatch_one(part))
    return "\n".join(outputs)


def _dispatch_one(part):
    global _STATE
    tokens = part.split()
    if not tokens:
        return ""
    op = tokens[0]

    if op == "help":
        return HELP_TEXT
    if op == "new":
        seed = int(tokens[1]) if len(tokens) > 1 else None
        weeks = int(tokens[2]) if len(tokens) > 2 else 5
        _STATE = fresh_state(seed=seed, weeks=weeks)
        return ("一局新的金丝笼开始了。你是权力者身边的宠臣，手里握着几张你在乎的牌。\n" +
                render_status(_STATE))
    if op == "import_save":
        _STATE = import_save(tokens[1])
        return "存档已恢复。\n" + render_status(_STATE)
    if op == "export":
        return export_save(_STATE)

    s = _STATE
    if op == "status":
        return render_status(s)
    if op == "board":
        return render_board(s)
    if op == "approach":
        return render_approach(s, int(tokens[1]))
    if op == "preview":
        return cmd_preview(s, int(tokens[1]), int(tokens[2]), tokens[3])
    if op == "dispatch":
        return cmd_dispatch(s, int(tokens[1]), int(tokens[2]), tokens[3])
    if op == "talk":
        return cmd_talk(s, tokens[1])
    if op == "endday":
        return cmd_endday(s)
    if op == "pay":
        return cmd_pay(s)
    if op == "sacrifice":
        return cmd_sacrifice(s, tokens[1])
    if op == "defy":
        return cmd_defy(s)
    if op == "sell":
        return cmd_sell(s, tokens[1])
    if op == "folio":
        return render_folio(s)
    if op == "chronicle":
        n = int(tokens[1]) if len(tokens) > 1 else 10
        return render_chronicle(s, n)
    if op == "ending":
        return render_ending(s)

    return "不认识这个指令，help 看看有哪些。"


def new_game(seed=None, weeks=5):
    return _dispatch_one("new%s%s" % (" " + str(seed) if seed is not None else "",
                                        " " + str(weeks) if seed is not None else (" " + str(weeks) if weeks != 5 else "")))


if __name__ == "__main__":
    print(cmd("help"))
