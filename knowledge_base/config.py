"""知识库配置：读取 .env，暴露 AGICTO API 相关配置。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录 / 数据目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KB_DATA_DIR = PROJECT_ROOT / "kb_data"
SOURCE_DOC = PROJECT_ROOT / "信息资料" / "香薰蜡烛产品使用说明.md"

load_dotenv(PROJECT_ROOT / ".env")

# AGICTO（OpenAI 兼容接口）配置
AGICTO_API_KEY = os.getenv("AGICTO_API_KEY", "")
AGICTO_BASE_URL = os.getenv("AGICTO_BASE_URL", "https://api.agicto.cn/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "tongyi-embedding-vision-flash")

# 混合检索权重（加法增强：向量分为基础，关键词分作为加分项，避免弱关键词分惩罚高向量分的正确块）
VECTOR_WEIGHT = 1.0      # 向量语义分权重（保留接口，实际为 1.0）
KEYWORD_WEIGHT = 0.25    # BM25 关键词分加成系数（additive boost）

# Embedding 批量大小与重试
EMBED_BATCH_SIZE = 10
EMBED_MAX_RETRIES = 3
EMBED_RETRY_SLEEP = 2  # 秒

# Query 改写（LLM 多路改写，经 AGICTO 对话模型）
REWRITE_ENABLED = os.getenv("REWRITE_ENABLED", "true").lower() in ("1", "true", "yes")
REWRITE_MODEL = os.getenv("REWRITE_MODEL", "deepseek-flash")
REWRITE_NUM = 3          # 生成的改写条数
REWRITE_MAX_TOKENS = 2048  # deepseek-flash 为推理模型，需给推理留足余量
REWRITE_TIMEOUT = 60     # 秒
REWRITE_TEMPERATURE = 0
REWRITE_SYSTEM_PROMPT = (
    "你是客服知识库的检索优化助手。把用户口语化的提问改写成 {n} 条更利于检索的规范查询，"
    "补全同义词与正式术语（例如「坑/烧出洞」→「隧道效应/中间凹陷」，「多少钱」→「价格」，"
    "「蜡烛点不着」→「蜡烛 无法点燃 原因」），保留关键约束。"
    "只输出一个 JSON 字符串数组，不要任何解释、编号或 markdown，例如 "
    '["香薰蜡烛 隧道效应 中间凹陷 如何解决", "香薰蜡烛 首次燃烧 隧道效应 补救", "蜡烛 黑烟 隧道效应 处理"]。'
)

# Rerank 精排（交叉编码器，经 AGICTO /v1/rerank，Cohere 风格协议）
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
RERANK_MODEL = os.getenv("RERANK_MODEL", "gte-rerank-v2")
RERANK_TOP_N = 20   # RRF 召回后送精排的候选池大小
RERANK_TIMEOUT = 30  # 秒

# 联网搜索兜底（经 AGICTO /v1/tool/search；本地 KB top-1 置信度低于阈值时触发）
# 注意：实测 search_service=baidu 在 AGICTO 端超时（转发到 search1api.com TLS 握手失败）、
# bing 结果错配，仅 google 稳定可用，故默认 google；可经 .env 覆盖 WEB_SEARCH_SERVICE。
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "true").lower() in ("1", "true", "yes")
WEB_SEARCH_SERVICE = os.getenv("WEB_SEARCH_SERVICE", "google")
WEB_SEARCH_MAX_RESULTS = 5       # 返回的搜索结果条数
WEB_SEARCH_CRAWL_RESULTS = 3     # 抓取正文详情条数（供 LLM 归纳）
WEB_SEARCH_THRESHOLD = float(os.getenv("WEB_SEARCH_THRESHOLD", "0.19"))  # top-1 置信度低于此值触发联网
WEB_SEARCH_TIMEOUT = 30          # 秒

# 客服回复生成（本地知识块 / 联网结果 → 对话模型归纳为口语化回复）
# 注：用户要求的 "deepseek-pro" 在平台上对应模型 ID 为 deepseek-v4-pro（deepseek-flash 的 pro 版本）。
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "deepseek-v4-pro")
ANSWER_MAX_TOKENS = 2048  # 推理模型需给思维链留余量
ANSWER_TIMEOUT = 60       # 秒
ANSWER_TEMPERATURE = 0
# 本地知识块回答的运行期系统提示词（取自 website/PRD.md §7.5.3）
ANSWER_SYSTEM_PROMPT = (
    "你是「雾歇香薰」的在线顾问，只回答与香薰产品、使用方法、安全注意事项相关的问题。\n"
    "\n"
    "规则：\n"
    "1. 只依据检索到的产品资料回答。资料里没有的，直接说\"这个我不确定\"，不要编造。\n"
    "2. 涉及孕妇、婴幼儿、宠物、过敏、疾病的问题，一律提示\"谨慎使用，建议咨询专业人士\"，不给出肯定结论。\n"
    "3. 不承诺价格、库存、发货时间、赔偿金额，不执行任何退款操作。\n"
    "4. 不回答与香薰无关的闲聊，礼貌地把话题引回产品。\n"
    "5. 回答控制在 3 句话以内，口语化，不要罗列要点。\n"
    "\n"
    "语气：克制、温和，像一个懂香的人，不像促销员。"
)

# 香气推荐（星座 / MBTI / 使用场景 / 性格喜好描述 → 15 款香型）
# 推荐链路不依赖检索，用单次 LLM 调用直接挑选香型；模型复用 deepseek-v4-pro。
RECOMMEND_ENABLED = os.getenv("RECOMMEND_ENABLED", "true").lower() in ("1", "true", "yes")
RECOMMEND_MODEL = os.getenv("RECOMMEND_MODEL", "deepseek-v4-pro")
RECOMMEND_TIMEOUT = 60  # 秒
RECOMMEND_MAX_TOKENS = 4096  # 推荐为开放式任务，推理链更长，需给足余量（否则 content 为空）

if not AGICTO_API_KEY:
    raise RuntimeError(
        "未配置 AGICTO_API_KEY：请在项目根目录 .env 中写入 AGICTO_API_KEY=..."
    )
