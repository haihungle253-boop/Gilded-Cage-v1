# 金丝笼（独立版）· 路线图与实施笔记

> 撰写：阿克 · 2026-07-06
> 状态：Phase 1（最小可玩）已完成并跑通自动化全流程测试

---

## 一、当前实现范围（Phase 1）

- 单人局：一个"宠臣"管理4张角色卡，独立于 Island Universe 内部「金丝笼」板块（那是 DOM+localStorage+LLM 的浏览器实现，本项目是零依赖的纯 Python 重写，只借鉴设计哲学，代码完全独立）
- 三层架构：规则引擎（`engine.py` 的状态机部分，纯函数、确定性）／内容供给（`ContentProvider` 接口，当前只有 `StaticPoolProvider`）／叙事渲染（模板拼接文本，非 LLM）
- 完整核心循环：命令卡→场所事件（三选二 approach）→掷骰结算→夜谈→审判日（pay/sacrifice/defy）→结局
- 弑君线（3步事件链）、猜疑隐藏值、永久死亡+墓志铭、珍宝掉落与变卖
- 存档 export/import（base64 JSON）

已用自动化脚本跑通：3周/5周整局、资源不足触发 defy、sacrifice 正确扣卡、弑君线解锁条件、存档 roundtrip。

---

## 二、ContentProvider 扩展路径（混合方案 A+B 的落地方式）

`engine.py` 里的 `ContentProvider` 抽象类只有三个方法：`draw_command` / `draw_board` / `make_card`。规则引擎（掷骰、验收判定、结局触发）只调用这三个方法拿到的结构化数据，不关心数据从哪来。这意味着：

```python
class LLMProvider(ContentProvider):
    def draw_command(self, week, total_weeks, r):
        raw = call_llm(...)          # 生成 JSON
        return _validate_command(raw)  # 复用与 StaticPoolProvider 相同的 clamp/校验函数

class HybridProvider(ContentProvider):
    def __init__(self, llm, fallback):
        self.llm, self.fallback = llm, fallback
    def draw_command(self, week, total_weeks, r):
        try:
            return self.llm.draw_command(week, total_weeks, r)
        except Exception:
            return self.fallback.draw_command(week, total_weeks, r)
```

**要做的事（按优先级）：**
1. 把 `StaticPoolProvider` 里散落的数值边界（难度4-14、资源缩放曲线等）提炼成独立的 `_validate_*` 校验函数——现在校验和生成逻辑还揉在一起，LLM 生成的内容必须过同一关，这是"防止AI又当裁判又当选手"的生命线，照抄了金丝笼企划书里的教训。
2. 实现 `LLMProvider`：复用 IU 项目里已经验证过的 prompt 设计思路（编剧只在生成时刻发挥创造力，产物经校验后固化），但这次输出目标是 Python dict/JSON，不是给浏览器用的格式。
3. `HybridProvider` 兜底：无 key 或调用失败自动回落 `StaticPoolProvider`，保证游戏永远可玩，这也是"零依赖"承诺的底线。
4. `narrate_day` 也可以做成同样的 Provider 化——现在是模板拼句子，以后可以换成 LLM 叙事渲染，规则引擎完全无感知。

---

## 三、AI + 人类协作玩法（Phase 3，尚未设计细节，先记录方向）

几个可能的形态，值得先讨论清楚再动手，别急着选：

- **多宠臣模式**：多个 agent（AI角色/人类）各自管理一叠角色卡，共享同一个"权力者"和命令卡池；命令卡可以是"全体宠臣里挑一个执行"，制造宠臣之间的博弈（抢功、甩锅、结盟）
- **旁观造物主模式**：人类不玩宠臣，而是像瓶中生态那样做"权力者"本人——决定命令卡怎么下、猜疑值怎么给，AI角色是被支配的一方；这个形态其实更接近瓶中生态"造物主看着系统演化"的体验，值得单独评估
- **IU 联动**：如果多个 story world 的 AI 角色（比如阿鸦这样的角色）被扔进同一局金丝笼当宠臣，牌面可以直接由角色库导入（复用 IU「金丝笼」企划书里 B③混合来源的思路），献祭的分量会因为角色本身有"历史"而完全不同

这几个方向互相不冲突，但会牵扯不同的状态结构（单 state → 多 state 或共享 state），建议先用 Phase 1 引擎多玩几局攒手感，再回头定型。

---

## 四、自动化 playtest 中发现的平衡性问题（诚实记录，未修复）

1. **"永远挑最高成功率"的贪心打法几乎不会失手。** 用 `preview` 遍历全部 卡×approach 组合、每次选最高成功率那个的策略，跑了 70 次检定 70 次全过。说明当前 4 张卡 × 每事件2种应对 的组合密度，太容易找到接近保底成功的选项。建议后续：要么减少"简单"难度事件的比例，要么让高成功率选项伴随更明显的资源/羁绊代价，制造真正的两难，而不是"只要够聪明就零风险"。

2. **猜疑值在无失手局面下几乎不会上升。** 猜疑的正向来源目前只有"检定失败"和"密谋步骤失败"，如果像上面那样几乎不失手，猜疑会一直趴在 0 附近，隐藏机制形同虚设。建议：给部分"看似安全"的选项也附带小额猜疑成本（哪怕成功），或者让猜疑随周数被动缓慢上升，逼玩家即使打得再好也要面对它。

3. **献祭类命令可能出现结构性死局。** `filter.tag` 命中的卡如果已经被献祭光了（比如已经把唯一"挚爱"标记的卡献出去），后续再抽到同类型命令会导致无卡可献、只能 defy。这在4张卡的小规模下概率不低（实测在 seed=99 的一局里第2周就撞上了）。建议：给 sacrifice 类命令加一个"资源赎买"兜底选项（比如高额金币也能顶替，但代价远高于正常献祭），或者让编剧/内容池在生成命令时检查场上现存标记，避免直接判死局。

这三条都是数值/内容层面的问题，不是架构缺陷——留给下一轮迭代，不建议现在就动手改，先让 Emrys 实际玩几局、感受一下节奏再决定往哪个方向调。

---

## 五、已知未实现（对应原企划书的 Phase 2/3 内容，本项目里都还没做）

- 换皮系统（同一套规则跑不同世界观：修真宗门/末世庇护所/星际殖民舰……）
- 跨局传承（幸存者带着记忆进入新局）
- 玩家自己也是可献祭的卡（"噩梦模式"）
- 命令验收的 `item`/`deed` 类型（现在只有 `resource`/`sacrifice`）
- 卡牌翻面等纯视觉效果（本项目目前是纯文本，没有 UI 层）
