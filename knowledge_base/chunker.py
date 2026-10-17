"""Markdown 解析与切块 + 关键词提取。"""
import re
from dataclasses import dataclass, field, asdict

import jieba
import jieba.analyse

# 自定义词典：香型名、专业术语（保证分词不被切碎、关键词可靠命中）
CUSTOM_WORDS = [
    "香薰蜡烛", "烛芯", "烛芯剪", "灭烛罩", "灭烛钩",
    "隧道效应", "蘑菇头", "挂壁", "起霜", "大豆蜡", "石蜡", "棕榈蜡", "棉芯", "蜡池",
    "香精", "精油", "扩香", "留香", "香型", "香调", "前调", "中调", "后调",
    "檀木", "乌木", "木灰", "金木", "深海", "潮汐", "海石", "青玫", "墨绯",
    "眠莲", "桔子酒", "桃子", "柚子", "抹茶青柚", "椰子糯米",
    "礼盒", "保质期", "退换", "补发", "闪点", "芳樟醇", "柠檬烯",
    "IFRA", "SGS", "MSDS", "VOCs", "MMB", "tunneling", "增值税普通发票",
    "中通快递", "顺丰", "磨砂玻璃", "牛皮纸盒", "母婴空间", "婴儿", "婴幼儿",
    "猫科", "养猫", "呼吸道", "哮喘", "过敏", "孕妇", "备孕", "哺乳期",
]
for w in CUSTOM_WORDS:
    jieba.add_word(w)

# 人工规则词表：关键词提取时直接叠加
RULE_KEYWORDS = [
    "隧道效应", "tunneling", "烛芯", "修剪", "蘑菇头", "黑烟", "灭烛罩", "灭烛钩",
    "大豆蜡", "石蜡", "IFRA", "SGS", "MSDS", "无铅", "棉芯", "保质期", "礼盒",
    "藤条", "翻转", "扩香", "留香", "闪点", "退换", "补发", "发票", "孕妇",
    "婴幼儿", "养猫", "哮喘", "过敏", "中通", "顺丰", "磨砂玻璃", "二次利用",
    "檀木", "乌木", "木灰", "金木", "深海", "潮汐", "海石", "青玫", "墨绯",
    "眠莲", "桔子酒", "桃子", "柚子", "抹茶青柚", "椰子糯米",
    "助眠", "冥想", "新手", "盲选",
]

KEYWORDS_PER_CHUNK = 10


@dataclass
class Chunk:
    id: int
    category: str   # 所属 ## 大章标题
    title: str      # 所属 ### 小节标题
    content: str
    source_path: str
    keywords: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def embed_text(self) -> str:
        """送入 embedding 模型的文本：标题 + 正文 + 关键词前置增强语义。"""
        kw = "、".join(self.keywords)
        return f"{self.title}\n{self.content}\n关键词：{kw}"


def _table_row_to_text(header, row):
    return "；".join(f"{h}：{v}" for h, v in zip(header, row) if v.strip())


def _parse_table(lines, i):
    """从 lines[i] 开始解析 Markdown 表格，返回 (自然语言行列表, 下一行索引)。"""
    rows = []
    header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
    i += 2  # 跳过表头与分隔行
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append(_table_row_to_text(header, cells))
        i += 1
    return rows, i


def _extract_keywords(text: str, limit: int = KEYWORDS_PER_CHUNK) -> list:
    kws = jieba.analyse.extract_tags(text, topK=limit)
    # 叠加人工规则词表命中项
    for rk in RULE_KEYWORDS:
        if rk in text and rk not in kws:
            kws.append(rk)
    return kws[: limit + 8]  # 允许规则词适当超出


def _split_long_content(content: str, max_len: int = 500) -> list:
    """内容过长时按段落边界拆分，每块尽量不超过 max_len 字。"""
    if len(content) <= max_len:
        return [content]
    parts, buf = [], ""
    for para in content.split("\n"):
        if len(buf) + len(para) > max_len and buf:
            parts.append(buf.strip())
            buf = ""
        buf += para + "\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def parse_markdown(md_path: str) -> list:
    """按 ## / ### 标题层级切块，表格转自然语言行。"""
    with open(md_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    chunks, category, title, buf = [], "", "", []
    cid = 0
    skip_until_next_heading = False

    def flush():
        nonlocal cid, buf
        if not buf or not any(l.strip() for l in buf):
            buf = []
            return
        content = "\n".join(buf).strip()
        for part in _split_long_content(content):
            chunks.append(Chunk(
                id=cid, category=category or "通用", title=title or category,
                content=part, source_path=str(md_path),
                keywords=_extract_keywords(part),
            ))
            cid += 1
        buf = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            flush()
            category = line[3:].strip()
            title = ""
            # 「参考来源」只是引用列表，不入知识库
            skip_until_next_heading = category.startswith("参考来源")
        elif line.startswith("### "):
            flush()
            title = line[4:].strip()
            skip_until_next_heading = False
        elif skip_until_next_heading:
            pass  # 跳过参考来源章节的列表内容
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").replace(":", "").strip()) <= {"-", " "}:
            flush()  # 表格独立处理
            rows, i = _parse_table(lines, i)
            for r in rows:
                if r.strip():
                    chunks.append(Chunk(
                        id=cid, category=category or "通用", title=title or category,
                        content=r, source_path=str(md_path),
                        keywords=_extract_keywords(r),
                    ))
                    cid += 1
            continue  # _parse_table 已推进 i
        elif line.startswith("# ") or line.strip() == "---":
            flush()
        else:
            buf.append(line)
        i += 1
    flush()
    return chunks
