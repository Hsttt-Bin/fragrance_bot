"""香气推荐：根据星座 / MBTI / 使用场景 / 性格喜好描述，推荐 15 款香型中的 1-3 款。

推荐链路不依赖检索，也不建「星座→香调」映射表——星座/MBTI 的性格特质交给 LLM（deepseek-v4-pro）
自行推断，香型侧用 推荐数据/scents.json 兜底（防止模型编造不存在的香型）。流程：
  前置分流 is_recommend_intent() → extract_dims() 统计已提供维度 → 不足两个维度时 build_followup() 追问
  → 凑齐后 recommend() 单次 LLM 调用出推荐；失败返回 None 由调用方降级回原 RAG。
"""
import json

from . import config
from .answerer import _chat

# 15 款香型结构化数据（推荐数据/scents.json），模块内缓存
_SCENTS_PATH = config.PROJECT_ROOT / "推荐数据" / "scents.json"
_scents_cache = None


def _load_scents() -> list:
    global _scents_cache
    if _scents_cache is None:
        try:
            _scents_cache = json.loads(_SCENTS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[recommend] 读取 scents.json 失败：{e}")
            _scents_cache = []
    return _scents_cache


# —— 词汇表 ——

# 12 星座：全名 + 省「座」写法（统一归一到全名）。全名放前面，保证「天蝎座」先于「天蝎」命中。
ZODIAC = {
    "白羊座": "白羊座", "白羊": "白羊座",
    "金牛座": "金牛座", "金牛": "金牛座",
    "双子座": "双子座", "双子": "双子座",
    "巨蟹座": "巨蟹座", "巨蟹": "巨蟹座",
    "狮子座": "狮子座", "狮子": "狮子座",
    "处女座": "处女座", "处女": "处女座",
    "天秤座": "天秤座", "天秤": "天秤座",
    "天蝎座": "天蝎座", "天蝎": "天蝎座",
    "射手座": "射手座", "射手": "射手座",
    "摩羯座": "摩羯座", "摩羯": "摩羯座",
    "水瓶座": "水瓶座", "水瓶": "水瓶座",
    "双鱼座": "双鱼座", "双鱼": "双鱼座",
}

# 16 个 MBTI 代码（大小写不敏感）
MBTI_CODES = [
    "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
]

# 使用场景词（与商品数据 scene_tags 一致，另补常见口语说法）
SCENE_WORDS = [
    "卧室", "书房", "客厅", "冥想", "茶室", "下午茶", "送礼", "办公", "餐厅",
    "浴室", "夏季", "约会", "泡澡", "派对", "餐桌", "摆件", "纪念",
    "助眠", "学习", "睡觉", "睡前", "工作", "加班",
]

# 性格 / 喜好描述词：命中即视为用户提供了「性格喜好」这个信息维度
PERSONA_WORDS = [
    "内向", "外向", "安静", "浪漫", "清冷", "治愈", "失眠", "解压", "仪式感",
    "沉稳", "成熟", "温柔", "活泼", "开朗", "独处", "看书", "文艺", "精致",
    "慵懒", "放松", "高级", "冷淡", "忧郁", "干净", "清爽", "温暖", "热烈",
    "神秘", "低调", "小众", "个性", "热情", "理性", "感性", "敏感", "佛系",
]

# 推荐意图词：与场景词 / 性格词连用才触发推荐；单独出现（如「卧室能点蜡烛吗」）不算
INTENT_WORDS = [
    "推荐", "适合", "想买", "选", "挑", "求推荐", "帮我选", "帮我挑",
    "买哪", "哪个好", "什么香", "哪款", "怎么选", "搭配",
]

# 推荐系统提示词：只从 15 款里选、不编造、带理由与价位、口语化
RECOMMEND_SYSTEM_PROMPT = (
    "你是「雾歇香薰」的在线顾问，负责根据用户提供的星座、MBTI、使用场景以及性格喜好描述推荐香型。\n"
    "\n"
    "规则：\n"
    "1. 只从下面提供的 15 款香型里挑选，绝不能编造不在此列表中的香型或价位。\n"
    "2. 结合星座/MBTI 的性格特质、用户自述的性格喜好、使用场景，对照每款香型的「香调/场景/人群」标签，挑最贴合的 1-3 款。\n"
    "3. 每款说明贴合理由（为什么适合），并带出价位（99/119/79/69 元）。\n"
    "4. 不要罗列要点，回答控制在 3 句话以内，口语化，语气克制、温和，像一个懂香的人，不像促销员。\n"
    "5. 若信息仍不足以判断，就按已有信息给出最贴合的建议，不要反复追问。\n"
    "6. 直接给出结论，不要反复权衡、不要输出分析过程。\n"
)


def extract_dims(query: str) -> dict:
    """从用户提问里提取已提供的信息维度：星座 / mbti / 场景 / 性格。"""
    dims = {"星座": None, "mbti": None, "场景": [], "性格": False}
    if not query:
        return dims
    # 星座：按 ZODIAC 顺序匹配（全名在前），命中第一个即停
    for key, full in ZODIAC.items():
        if key in query:
            dims["星座"] = full
            break
    # MBTI：大小写不敏感
    up = query.upper()
    for code in MBTI_CODES:
        if code in up:
            dims["mbti"] = code
            break
    # 场景（可命中多个）
    dims["场景"] = [w for w in SCENE_WORDS if w in query]
    # 性格 / 喜好描述：命中即 True
    dims["性格"] = any(w in query for w in PERSONA_WORDS)
    return dims


def _has_info(dims: dict) -> bool:
    """是否有任意一个维度命中（用于判断用户是否在回答追问）。"""
    return bool(dims["星座"] or dims["mbti"] or dims["场景"] or dims["性格"])


def _filled_count(dims: dict) -> int:
    """统计已提供的信息维度个数（星座 / MBTI / 场景 / 性格，各算一个）。"""
    return (
        (1 if dims["星座"] else 0)
        + (1 if dims["mbti"] else 0)
        + (1 if dims["场景"] else 0)
        + (1 if dims["性格"] else 0)
    )


def is_recommend_intent(query: str) -> bool:
    """判断提问是否属于香气推荐意图。"""
    dims = extract_dims(query)
    # 星座 / MBTI 命中即推荐
    if dims["星座"] or dims["mbti"]:
        return True
    # 场景词 或 性格词 命中 + 推荐意图词 → 推荐
    has_scene_or_persona = bool(dims["场景"]) or dims["性格"]
    has_intent = any(w in query for w in INTENT_WORDS)
    return has_scene_or_persona and has_intent


def build_followup(dims: dict) -> str | None:
    """统计已提供维度，不足两个时给出追问；≥2 个返回 None（可直接推荐）。"""
    filled = _filled_count(dims)
    if filled >= 2:
        return None
    # 只有一个维度：按已有项补问缺失信息
    if dims["星座"]:
        return "想放在什么场景用呢？比如卧室、书房还是送礼～也可以告诉我你的 MBTI"
    if dims["mbti"]:
        return "主要想在什么场景用呢？卧室、书房还是送礼？"
    if dims["场景"]:
        return "方便告诉我你的星座或 MBTI 吗？这样能推荐得更贴合你～"
    # 只有性格 / 喜好描述
    return "方便告诉我你的星座或 MBTI 吗？或者说说主要在什么场景用～"


def merge_dims(acc: dict, new: dict) -> dict:
    """把新一轮提取的维度合并进累计状态（星座/MBTI 取首个，场景取并集，性格取或）。"""
    merged = dict(acc)
    if new["星座"] and not merged["星座"]:
        merged["星座"] = new["星座"]
    if new["mbti"] and not merged["mbti"]:
        merged["mbti"] = new["mbti"]
    merged["场景"] = sorted(set(merged["场景"]) | set(new["场景"]))
    merged["性格"] = merged["性格"] or new["性格"]
    return merged


def recommend(texts: list, dims: dict) -> str | None:
    """基于已收集的信息（用户原话 + 维度）单次调用 LLM 生成推荐回复；失败返回 None。"""
    scents = _load_scents()
    if not scents:
        return None
    context = json.dumps(scents, ensure_ascii=False, indent=2)

    dim_lines = []
    if dims["星座"]:
        dim_lines.append(f"星座：{dims['星座']}")
    if dims["mbti"]:
        dim_lines.append(f"MBTI：{dims['mbti']}")
    if dims["场景"]:
        dim_lines.append(f"使用场景：{'、'.join(dims['场景'])}")
    if dims["性格"]:
        dim_lines.append("用户有性格/喜好相关描述（见用户原话）")
    dim_text = "\n".join(dim_lines) if dim_lines else "（无）"

    user_texts = "\n".join(f"- {t}" for t in texts if t)
    messages = [
        {"role": "system", "content": RECOMMEND_SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"以下是本店 15 款香型的完整数据（JSON）：\n{context}\n\n"
            f"用户提供的信息：\n{dim_text}\n\n"
            f"用户原话：\n{user_texts}"
        )},
    ]
    return _chat(
        messages,
        model=config.RECOMMEND_MODEL,
        timeout=config.RECOMMEND_TIMEOUT,
        max_tokens=config.RECOMMEND_MAX_TOKENS,
    )
