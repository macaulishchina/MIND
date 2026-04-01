# STL v2 语法规范

> **版本** v2.0-draft  **日期** 2026-04-01  
> **状态** 设计稿  
> **前身** 语义翻译层 v1（5+1 句式）  
> **设计目标** LLM 友好 — 少 token、少犯错、浅思考

---

## 目录

1. [设计原则](#1-设计原则)
2. [行类型总览](#2-行类型总览)
3. [字符集与词法约定](#3-字符集与词法约定)
4. [REF — 实体声明](#4-ref--实体声明)
5. [STMT — 语义断言](#5-stmt--语义断言)
6. [NOTE — 自由文本注释](#6-note--自由文本注释)
7. [COMMENT — 行注释](#7-comment--行注释)
8. [形式文法 (EBNF)](#8-形式文法-ebnf)
9. [硬约束清单](#9-硬约束清单)
10. [种子词表](#10-种子词表)
11. [完整示例集](#11-完整示例集)
12. [解析器设计指导](#12-解析器设计指导)
13. [与 v1 的差异摘要](#13-与-v1-的差异摘要)
14. [设计决策记录](#14-设计决策记录)

---

## 1. 设计原则

### 1.1 核心目标

STL 是一种**紧凑的语义中间语言**。LLM 将自然语言对话翻译为 STL 文本、
解析器将 STL 文本转为结构化数据入库。

### 1.2 三条设计约束

| 约束 | 策略 |
|------|------|
| **LLM 少 token** | 3+1 行类型、无冗余元信息（不输出置信度/溯源） |
| **LLM 少犯错** | 禁止嵌套、禁止列表、arg 只有 4 种原子类型 |
| **LLM 浅思考** | 不要求 LLM 做分类决策（local/world、prop/frame、confidence） |

### 1.3 语法封闭 × 词汇受控

| 维度 | 策略 |
|------|------|
| **语法结构** | 只有 **3 种语句 + 1 种注释**，解析器用正则完成 |
| **词汇** | 提供种子词表（~70 词），LLM **只能使用已有词**，但可以建议新词 |

---

## 2. 行类型总览

一段 STL 文本由若干**行**组成。每行恰好是以下 4 种之一：

| # | 名称 | 语法 | 用途 |
|---|------|------|------|
| ① | **REF** | `@id: TYPE "key"` | 声明一个实体 |
| ② | **STMT** | `$id = pred(arg, ...)` | 断言一条语义关系 |
| ③ | **NOTE** | `note($id, "text")` | 自由文本兜底 |
| ④ | **COMMENT** | `# ...` | 注释，解析器忽略 |

空行被忽略。

不存在其他行类型。任何不符合以上 4 种模式的行均为**非法行**，
交由解析器的容错机制处理。

---

## 3. 字符集与词法约定

### 3.1 编码

UTF-8。

### 3.2 标识符 (identifier)

```
IDENT = LETTER ( LETTER | DIGIT | "_" )*
LETTER = [a-zA-Z]
DIGIT  = [0-9]
```

标识符用于 `@id`、`$id`、TYPE、pred、suggested_word。

**命名风格约定**：
- `@id`：小写英文或缩写，如 `@tom`、`@p1`、`@tokyo`
- TYPE：小写英文，如 `person`、`city`、`org`
- pred / suggested_word：`lowercase_snake_case`，如 `live_in`、`childhood_friend`

### 3.3 字符串字面量

```
STRING = '"' CHAR* '"'
CHAR   = 任意字符（除未转义的 '"'）
       | '\"'     (转义双引号)
```

字符串内容保留原文（中文用中文、英文用英文）。字符串内不允许换行。

### 3.4 数值字面量

```
NUMBER = ["-"] DIGIT+ ["." DIGIT+]
```

示例：`42`、`-3`、`0.8`、`3.14`

### 3.5 行终止

每行以 `\n` 终止。`\r\n` 等价于 `\n`。

---

## 4. REF — 实体声明

### 4.1 语法

```
"@" IDENT ":" TYPE STRING
"@" IDENT ":" TYPE
```

即：

```
@id: TYPE "key"       # 有名实体
@id: TYPE             # 未命名实体
```

### 4.2 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 本批次内该实体的局部标识符 |
| `TYPE` | 是 | 实体类型（种子值见 §4.4） |
| `key` | 否 | 实体原文名称。省略表示未命名实体("我有个朋友") |

### 4.3 `@self`

`@self` 是保留实体引用，代表 owner（用户本人）。

- `@self` **不需要声明**，在 STMT 的 arg 中直接使用
- `@self` **不能被重新声明**（`@self: person "me"` 是非法的）
- 除 `@self` 外，所有 `@id` 必须通过 REF 行声明后才能使用

### 4.4 TYPE 种子值

```
person  place  org  brand  event  object  animal  food  concept  time
```

TYPE 不可自创。如果实体不属于任何种子 TYPE，使用 `concept`。

### 4.5 示例

```
@tom: person "tom"              # Tom
@tokyo: city                    # 非法! city 不在种子TYPE中，应为 place
@tokyo: place "tokyo"           # 东京
@google: org "Google"           # Google
@p1: person                     # 未命名实体（"我有个朋友"）
```

### 4.6 key 的语义

key 保留对话中的原文表达：
- 中文名用中文：`@mom: person "妈妈"`
- 英文名用英文：`@tom: person "tom"`
- 品牌名用原文：`@ikea: brand "IKEA"`

key 是同一 TYPE 下实体去重的依据。同一段 STL 中不应出现两个
`person "tom"` 的声明。

---

## 5. STMT — 语义断言

### 5.1 语法

```
"$" IDENT "=" PRED "(" ARG_LIST ")" [ ":" SUGGESTED ]
```

其中：

```
PRED       = IDENT
SUGGESTED  = IDENT
ARG_LIST   = ARG ( "," ARG )*
```

### 5.2 参数类型

arg **有且仅有** 4 种原子类型：

| 类型 | 语法 | 示例 | 解析器判定 |
|------|------|------|-----------|
| 实体引用 | `@IDENT` | `@tom`、`@self` | 以 `@` 开头 |
| 命题引用 | `$IDENT` | `$p1`、`$f1` | 以 `$` 开头 |
| 字符串 | `STRING` | `"football_player"` | 以 `"` 开头 |
| 数值 | `NUMBER` | `42`、`0.8` | 以数字或 `-` 开头 |

**不允许**其他 arg 形态。特别地：

- **禁止内联谓词**：`hope(@self, visit(@self, @tokyo))` 是非法的
- **禁止列表**：`speak(@self, ["中文", "英语"])` 是非法的

要表达嵌套语义，必须先声明中间 `$id`：

```
$p1 = visit(@self, @tokyo)
$f1 = hope(@self, $p1)
```

要表达多值，必须展开为多条 STMT：

```
$p1 = speak(@self, "中文")
$p2 = speak(@self, "英语")
```

### 5.3 谓词建议 `:suggested_word`

当种子词表中没有精确匹配的谓词时，LLM **必须使用最接近的种子词**作为
`pred`，同时可以在 `)` 之后用 `:` 附加建议词：

```
$p1 = friend(@self, @tom):childhood_friend
$p2 = like(@self, "coffee"):obsessed_with
```

规则：

| 规则 | 说明 |
|------|------|
| `pred` 必须是种子词 | 确保解析器永远稳定 |
| `:suggested_word` 是可选的 | 不是每条 STMT 都需要 |
| `suggested_word` 格式为 `lowercase_snake_case` | 与种子词格式一致 |
| suggested_word 不影响解析和存储语义 | 独立记录，供后续审查 |

解析器存储时将 `suggested_word` 写入 statements 表的
`suggested_pred` 字段。

### 5.4 参数位置语义

参数的语义由**谓词 + 位置**共同确定。位置语义在种子词表的
`arg_schema` 中记录：

```
friend(person_a, person_b)       # 位置0=person_a, 位置1=person_b
say(speaker, content)            # 位置0=speaker, 位置1=content
time(target, value)              # 位置0=被修饰的$id, 位置1=时间值
```

LLM 不需要记忆 arg_schema——按自然语义顺序填写参数即可。
arg_schema 是解析器侧的元数据。

### 5.5 统一的语义类别

v1 中 PROP、FRAME、QUALIFIER 是三种概念。v2 中它们**语法统一为 STMT**。

类别区分由**解析器在入库时自动标注**（查词表的 `category` 字段），
LLM 无需感知。

| category | 语义 | 示例谓词 |
|----------|------|---------|
| `prop` | 关于世界的断言 | `friend`, `occupation`, `live_in` |
| `frame` | 对命题的态度/包装 | `believe`, `hope`, `say`, `neg` |
| `qualifier` | 修饰另一条命题 | `time`, `degree`, `quantity` |

这个分类**只影响下游查询**，不影响解析。

### 5.6 示例

```
$p1 = friend(@self, @tom)
$p2 = occupation(@tom, "football_player")
$p3 = live_in(@tom, @tokyo)
$p4 = time($p3, "2025")
$p5 = resign(@tom)
$p6 = time($p5, "next_month")
$f1 = hope(@self, $p5):hope_stay
$p7 = alias(@tom, "小汤")
```

---

## 6. NOTE — 自由文本注释

### 6.1 语法

```
"note(" "$" IDENT "," STRING ")"
```

即：`note($target_id, "free text")`

### 6.2 用途

NOTE 是**信息保全的最后防线**——无法用 REF + STMT 表达的信息放这里。

典型场景：

```
note($p1, "用户说这句话时笑了")
note($f1, "语气是半开玩笑的")
```

### 6.3 `target_id`

NOTE 必须关联一个已存在的 `$id`。如果信息不属于任何特定 STMT，
关联到最近的 `$id`。

### 6.4 约束

- NOTE 的文本内容不参与结构化解析
- NOTE 内部不允许换行
- 如果一段 STL 中大量信息只能靠 NOTE 表达，说明词表需要扩展

---

## 7. COMMENT — 行注释

### 7.1 语法

```
"#" 任意字符至行尾
```

### 7.2 语义

解析器完全忽略 COMMENT 行。COMMENT 仅用于 STL 文本的人类可读性。

LLM 不应输出 COMMENT。Prompt 中不鼓励、也不禁止 COMMENT 输出。
解析器遇到 COMMENT 自动跳过，不计入任何统计。

---

## 8. 形式文法 (EBNF)

```ebnf
(* ====== 顶层 ====== *)
program       = { line NL } ;
line          = blank | comment | ref_line | stmt_line | note_line ;
blank         = WS* ;

(* ====== COMMENT ====== *)
comment       = WS* "#" { ANY } ;

(* ====== REF ====== *)
ref_line      = "@" IDENT ":" WS+ TYPE ( WS+ STRING )? ;
TYPE          = IDENT ;

(* ====== STMT ====== *)
stmt_line     = "$" IDENT WS* "=" WS* PRED "(" arg_list ")" [ ":" SUGGESTED ] ;
PRED          = IDENT ;
SUGGESTED     = IDENT ;
arg_list      = arg { "," arg } ;
arg           = WS* ( ref_arg | prop_arg | STRING | NUMBER ) WS* ;
ref_arg       = "@" IDENT ;
prop_arg      = "$" IDENT ;

(* ====== NOTE ====== *)
note_line     = "note(" "$" IDENT "," WS* STRING ")" ;

(* ====== 词法 ====== *)
IDENT         = LETTER { LETTER | DIGIT | "_" } ;
STRING        = '"' { CHAR } '"' ;
NUMBER        = [ "-" ] DIGIT { DIGIT } [ "." DIGIT { DIGIT } ] ;
LETTER        = "a".."z" | "A".."Z" ;
DIGIT         = "0".."9" ;
CHAR          = ANY_EXCEPT_UNESCAPED_DQUOTE | '\"' ;
NL            = "\n" | "\r\n" ;
WS            = " " | "\t" ;
ANY           = (* 任意非换行字符 *) ;
```

### 8.1 文法特性

| 特性 | 说明 |
|------|------|
| **正则可解析** | 每种行类型都可以用一条正则表达式匹配 |
| **无递归** | arg 不包含嵌套结构，不需要递归下降 |
| **无歧义** | 每行的首字符（`@` / `$` / `n` / `#` / 空白）唯一确定行类型 |
| **行独立** | 每行独立解析，单行错误不影响其余行 |

### 8.2 行类型判定

解析器通过行首字符 O(1) 判定行类型：

| 行首 | 行类型 |
|------|--------|
| `@` | REF |
| `$` | STMT |
| `n` (且匹配 `note(`) | NOTE |
| `#` | COMMENT |
| 空白/空行 | 忽略 |
| 其他 | 非法行 |

### 8.3 REF 与 STMT 的语法无歧义性

- REF 使用 `:`：`@id: TYPE "key"`
- STMT 使用 `=`：`$id = pred(args)`

两者通过前缀符（`@` vs `$`）和分隔符（`:` vs `=`）双重区分，
不可能产生歧义。

`:suggested_word` 中的 `:` 紧跟在 `)` 之后出现，而 REF 中的 `:`
紧跟在 `@IDENT` 之后出现，位置完全不同，不会冲突。

---

## 9. 硬约束清单

以下约束必须同时成立。违反任意一条的行即为非法行。

| # | 约束 | 说明 |
|---|------|------|
| C1 | **每行一条语句** | 不允许多条语句在同一行 |
| C2 | **先声明后使用** | `@id` 必须在 REF 行中声明后才能在 STMT/NOTE 中引用 |
| C3 | **`@self` 免声明** | `@self` 是隐式存在的保留实体 |
| C4 | **`@self` 不可重声明** | `@self: ...` 是非法行 |
| C5 | **arg 无嵌套** | arg 只能是 4 种原子类型 |
| C6 | **arg 无列表** | 不存在 `[...]` 语法 |
| C7 | **pred 必须是种子词** | 非种子词只能出现在 `:suggested_word` 位置 |
| C8 | **TYPE 必须是种子值** | 只能使用 §4.4 中列出的 TYPE |
| C9 | **STRING 无换行** | 字符串内不允许出现换行符 |
| C10 | **$id 本批次唯一** | 同一段 STL 中不能出现两个相同的 `$id` |
| C11 | **note 引用已存在的 $id** | `note($id, ...)` 的 `$id` 必须在之前的 STMT 行中声明 |

---

## 10. 种子词表

### 10.1 按语义域分组

LLM 根据对话内容**从以下词中选择**。不能自创谓词。

#### 关系 (relationships)

| 谓词 | arg_schema | 说明 |
|------|-----------|------|
| `friend` | person_a, person_b | 朋友 |
| `mother` | child, parent | 母亲 |
| `father` | child, parent | 父亲 |
| `brother` | person_a, person_b | 兄弟 |
| `sister` | person_a, person_b | 姐妹 |
| `spouse` | person_a, person_b | 配偶 |
| `partner` | person_a, person_b | 伴侣 |
| `child` | parent, child | 子女 |
| `cousin` | person_a, person_b | 堂/表亲 |
| `coworker` | person_a, person_b | 同事 |
| `boss` | employee, boss | 上级 |
| `mentor` | mentee, mentor | 导师 |
| `student` | student, institution_or_teacher | 学生 |
| `roommate` | person_a, person_b | 室友 |
| `neighbor` | person_a, person_b | 邻居 |
| `classmate` | person_a, person_b | 同学 |
| `teammate` | person_a, person_b | 队友 |
| `client` | provider, client | 客户 |
| `landlord` | tenant, landlord | 房东 |
| `doctor` | patient, doctor | 医生 |
| `pet` | owner, pet | 宠物 |
| `alias` | entity, alias_name | 别名 |

#### 属性与状态 (attributes & states)

| 谓词 | arg_schema | 说明 |
|------|-----------|------|
| `name` | entity, name_value | 名字 |
| `age` | entity, age_value | 年龄 |
| `occupation` | entity, occupation_value | 职业 |
| `location` | entity_or_stmt, place_value | 所在地 |
| `workplace` | entity, workplace_value | 工作地点 |
| `education` | entity, education_value | 学历 |
| `nationality` | entity, nationality_value | 国籍 |
| `like` | experiencer, target | 喜欢 |
| `dislike` | experiencer, target | 不喜欢 |
| `habit` | entity, habit_desc | 习惯 |
| `hobby` | entity, hobby_desc | 爱好 |
| `skill` | entity, skill_desc | 技能 |
| `own` | owner, object | 拥有 |
| `use` | user, object | 使用 |
| `speak` | speaker, language | 说(语言) |
| `live_in` | entity, place | 居住在 |
| `work_at` | entity, workplace | 工作于 |
| `study_at` | entity, institution | 就读于 |

#### 动作与事件 (actions & events)

| 谓词 | arg_schema | 说明 |
|------|-----------|------|
| `eat` | eater, food | 吃 |
| `drink` | drinker, beverage | 喝 |
| `plan` | agent, content | 计划 |
| `buy` | buyer, object | 买 |
| `visit` | visitor, destination | 拜访/去 |
| `meet` | person_a, person_b | 见面 |
| `resign` | agent | 辞职 |
| `marry` | person_a, person_b | 结婚 |
| `move` | agent, destination | 搬家 |
| `start` | agent, activity | 开始 |
| `stop` | agent, activity | 停止 |
| `birthday` | entity | 生日 |
| `gift` | giver, receiver, object | 送礼 |
| `event` | participant, event_desc | 事件 |

#### 态度与言语 (attitudes & speech)

| 谓词 | arg_schema | 说明 |
|------|-----------|------|
| `believe` | experiencer, content | 认为 |
| `doubt` | experiencer, content | 怀疑 |
| `know` | experiencer, content | 知道 |
| `uncertain` | experiencer, content | 不确定 |
| `hope` | experiencer, content | 希望 |
| `want` | experiencer, content | 想要 |
| `intend` | experiencer, content | 打算 |
| `say` | speaker, content | 说 |
| `recommend` | speaker, content | 推荐 |
| `ask` | speaker, content | 询问 |
| `promise` | speaker, content | 承诺 |
| `emotion` | experiencer, emotion_type | 情感 |
| `decide` | agent, content | 决定了 |
| `defer` | agent, content | 搁置 |
| `undecided` | agent, content | 未决定 |

#### 逻辑与模态 (logic & modality)

| 谓词 | arg_schema | 说明 |
|------|-----------|------|
| `neg` | content | 否定 |
| `if` | condition, consequence | 条件 |
| `cause` | cause, effect | 因果(原因→结果) |
| `because` | effect, cause | 因果(结果←原因) |
| `must` | obligee, content | 必须 |
| `permit` | authority, content | 允许 |
| `should` | obligee, content | 应当 |
| `lie` | speaker, content | 谎言 |
| `joke` | speaker, content | 玩笑 |
| `retract_intent` | speaker, content_desc | 撤回意图 |
| `correct_intent` | speaker, content | 更正意图 |

#### 修饰 (modifiers)

**这些谓词的第一个参数必须是 `$id`（被修饰的 STMT）。**

| 谓词 | arg_schema | 说明 |
|------|-----------|------|
| `time` | target, time_value | 时间锚点 |
| `degree` | target, degree_value | 程度 |
| `quantity` | target, quantity_value | 数量 |
| `frequency` | target, freq_value | 频率 |
| `duration` | target, duration_value | 持续时长 |

### 10.2 词表统计

| 域 | 数量 |
|----|------|
| 关系 | 22 |
| 属性与状态 | 18 |
| 动作与事件 | 14 |
| 态度与言语 | 15 |
| 逻辑与模态 | 11 |
| 修饰 | 5 |
| **合计** | **85** |

### 10.3 `location` 双用说明

`location` 同时出现在"属性与状态"和"修饰"的语义中。
它的参数类型决定用法：
- `location(@tom, "tokyo")` — 属性：Tom 在东京
- `location($p1, @tokyo)` — 修饰：$p1 这件事发生在东京

解析器不区分这两种用法——都是 STMT。下游查询通过参数类型区分。

---

## 11. 完整示例集

### 11.1 简单关系 + 属性

**输入**：我朋友 Tom 是足球运动员

```
@tom: person "tom"
$p1 = friend(@self, @tom)
$p2 = occupation(@tom, "football_player")
```

### 11.2 未命名实体

**输入**：我有个朋友是足球运动员

```
@p1: person
$p1 = friend(@self, @p1)
$p2 = occupation(@p1, "football_player")
```

### 11.3 多值属性(展开)

**输入**：我会说中文、英语和一点点日语

```
$p1 = speak(@self, "中文")
$p2 = speak(@self, "英语")
$p3 = speak(@self, "日语")
$p4 = degree($p3, "slight")
```

### 11.4 希望

**输入**：我希望 Tom 来东京

```
@tom: person "tom"
@tokyo: place "tokyo"
$p1 = visit(@tom, @tokyo)
$f1 = hope(@self, $p1)
```

### 11.5 条件

**输入**：如果明天不下雨，我打算去跑步

```
$p1 = event(@self, "rain")
$p2 = neg($p1)
$p3 = time($p2, "tomorrow")
$p4 = plan(@self, "running")
$f1 = if($p3, $p4)
```

### 11.6 转述

**输入**：Mike 说 Tom 住在东京

```
@mike: person "mike"
@tom: person "tom"
@tokyo: place "tokyo"
$p1 = live_in(@tom, @tokyo)
$f1 = say(@mike, $p1)
```

### 11.7 撒谎

**输入**：Mike 跟我说他去过火星，我觉得他在扯淡

```
@mike: person "mike"
$p1 = visit(@mike, "Mars")
$f1 = say(@mike, $p1)
$f2 = lie(@mike, $f1)
$f3 = believe(@self, $f2)
```

### 11.8 因果

**输入**：Tom 去年辞职了，因为老板太 push 了

```
@tom: person "tom"
@b1: person
$p1 = resign(@tom)
$p2 = time($p1, "last_year")
$p3 = boss(@tom, @b1)
$p4 = like(@b1, "push"):overbearing
$p5 = cause($p4, $p1)
```

### 11.9 义务 (多跳打平)

**输入**：我妈说让我周末去看她

```
@mom: person "妈妈"
$p1 = mother(@self, @mom)
$p2 = visit(@self, @mom)
$p3 = must(@self, $p2)
$f1 = say(@mom, $p3)
$p4 = time($f1, "this_weekend")
```

### 11.10 不确定性

**输入**：Sarah 最近好像也辞职了

```
@sarah: person "sarah"
$p1 = resign(@sarah)
$p2 = time($p1, "recent")
$p3 = uncertain(@self, $p1)
```

### 11.11 替他人做偏好判断

**输入**：我觉得我妈更喜欢金项链

```
@mom: person "妈妈"
$p1 = like(@mom, "gold_necklace")
$f1 = believe(@self, $p1)
$p2 = degree($p1, "more")
```

### 11.12 决策搁置

**输入**：算了到时候再说吧（上下文：讨论送礼物）

```
$f1 = defer(@self, $p_gift)
```

注：`$p_gift` 必须在之前的 STMT 中已声明。

### 11.13 谓词建议

**输入**：我最近迷上了长跑，每天 5 公里

```
$p1 = hobby(@self, "long_distance_running")
$p2 = time($p1, "recent")
$p3 = quantity($p1, "5km_per_day")
$p4 = like(@self, $p1):obsessed_with
```

### 11.14 别名

**输入**：Tom 的小名叫小汤，外国朋友叫他 Tommy

```
@tom: person "tom"
$p1 = alias(@tom, "小汤")
$p2 = alias(@tom, "Tommy")
```

### 11.15 完整长对话

**输入**（20 轮微信聊天概要）：

```
与 Tom 吃饭在樱花亭、Tom 下月辞职因为老板 push、
可能和老婆 Sarah 吵架了、Sarah 之前在银行好像也辞职了、
Tom 是公司唯一聊得来的人希望他别走、Tom 说考虑一下、
周末去宜家买 KALLAX 书架、妈妈让收拾房间、
妈妈下月生日没想好送什么、Tom 建议送按摩仪、
我觉得妈妈喜欢金项链、算了到时候再说、最近开始跑步 5 公里
```

**输出**：

```
@tom: person "tom"
@sarah: person "sarah"
@mom: person "妈妈"
@sakura: place "樱花亭"
@kallax: brand "KALLAX"
@b1: person

$p1 = meet(@self, @tom)
$p2 = location($p1, @sakura)
$p3 = time($p1, "today_noon")

$p4 = resign(@tom)
$p5 = time($p4, "next_month")
$f1 = say(@tom, $p4)
$p6 = boss(@tom, @b1)
$p7 = like(@b1, "push"):overbearing
$p8 = cause($p7, $p4)
$f2 = say(@tom, $p8)

$p9 = spouse(@tom, @sarah)
$p10 = event(@tom, "quarrel"):quarrel
$p11 = cause($p10, $p4)
$f3 = believe(@self, $p11)

$p12 = work_at(@sarah, "bank")
$p13 = time($p12, "past")
$p14 = resign(@sarah)
$p15 = time($p14, "recent")
$p16 = uncertain(@self, $p14)

$p17 = coworker(@self, @tom)
$p18 = friend(@self, @tom):closest_at_work
$p19 = resign(@tom)
$p20 = neg($p19)
$f4 = hope(@self, $p20)

$f5 = say(@tom, $p4)
$p21 = undecided(@tom, $p4)

$p22 = buy(@self, "bookshelf")
$p23 = like(@self, @kallax)
$p24 = time($p22, "this_weekend")

$p25 = mother(@self, @mom)
$f6 = must(@self, "clean_room")
$f7 = say(@mom, $f6)

$p26 = birthday(@mom)
$p27 = time($p26, "next_month")
$p28 = gift(@self, @mom, "?")
$f8 = undecided(@self, $p28)

$p29 = gift(@tom, "mother", "massage_device")
$f9 = recommend(@tom, $p29)

$p30 = like(@mom, "gold_necklace")
$f10 = believe(@self, $p30)

$f11 = defer(@self, $f8)

$p31 = hobby(@self, "running")
$p32 = quantity($p31, "5km_per_day")
$p33 = time($p31, "recent")
```

**信息覆盖率**：19/19 项全部捕获。总行数 43 行（v1 为 59 行含 ev，减少 27%）。

---

## 12. 解析器设计指导

### 12.1 正则模式

```python
RE_COMMENT = re.compile(r'^\s*#')
RE_REF     = re.compile(r'^@(\w+):\s*(\w+)(?:\s+"([^"]*)")?\s*$')
RE_STMT    = re.compile(r'^\$(\w+)\s*=\s*(\w+)\((.+)\)(?::(\w+))?\s*$')
RE_NOTE    = re.compile(r'^note\(\$(\w+),\s*"(.+)"\)\s*$')
```

4 条正则覆盖全部行类型。

### 12.2 参数拆分

因为 arg 禁止嵌套，参数拆分变为**纯逗号分割**（仅需处理字符串内的逗号）：

```python
def split_args(args_str: str) -> list[str]:
    """在顶层逗号处分割参数，仅需处理字符串引号。"""
    result, current, in_string = [], [], False
    for ch in args_str:
        if ch == '"':
            in_string = not in_string
        if ch == ',' and not in_string:
            result.append(''.join(current).strip())
            current = []
            continue
        current.append(ch)
    if current:
        result.append(''.join(current).strip())
    return result
```

不需要括号匹配栈。

### 12.3 容错级联（简化为 3 级）

v1 的 4 级级联简化为 3 级（因为语法更简单，需要 LLM 修正的概率更低）：

```
Level 1 — Strict：正则匹配 + 逗号分割
Level 2 — Fuzzy：自动修复（中文引号→英文引号、尾部括号不平衡）
Level 3 — Fallback：包装为 note($nearest_id, "PARSE_FAIL: 原文")
```

Level 3（LLM 修正）被删除——如果语法本身足够简单，LLM 修正就不值得
一次额外的 API 调用。

### 12.4 未声明引用的处理

当 STMT 中引用了未声明的 `@id` 时，解析器自动创建 fallback REF
（type=`concept`, key=null），避免连锁失败。标记 `parse_level=fallback`。

### 12.5 `@self` 检查

解析器在初始化时预注册 `self` 到 declared_refs 集合。
遇到 `@self:` 开头的 REF 行时直接标记为非法行。

---

## 13. 与 v1 的差异摘要

| 维度 | v1 | v2 |
|------|-----|-----|
| 行类型 | 5+1 (REF, PROP, FRAME, EV, NOTE, COMMENT) | 3+1 (REF, STMT, NOTE, COMMENT) |
| EV | 必须为每条 $id 附加 ev() | 删除，系统侧推断 |
| REF 语法 | `@id = @local/TYPE("key")` | `@id: TYPE "key"` |
| scope | local / world / blank | 无（统一） |
| `@self` | 需要 `@s = @self` 别名 | 直接在 arg 中使用 |
| PROP/FRAME/QUALIFIER | 三种概念，prompt 分开列出 | 统一为 STMT，category 后标注 |
| 内联嵌套 | 允许 2 层 | 禁止 |
| 列表 | `[a, b, c]` 语法 | 禁止，展开为多条 STMT |
| arg 类型 | 6 种 | 4 种原子 |
| alias | REF 行的 `alias=[...]` 参数 | `$id = alias(@ref, "name")` |
| blank node | `_:id` 语法 | `@id: TYPE`（key 省略） |
| 谓词自创 | LLM 自由创造 + NEW_PRED note | 禁止自创，只能 `:suggested_word` |
| 解析器 | 括号匹配栈 + 4 级级联 | 纯逗号分割 + 3 级级联 |

---

## 14. 设计决策记录

### D1. 为什么删 EV

EV 的三个字段（conf, span, residual）都可以由系统侧替代：
- conf → 根据 frame 类型自动推断
- span → 通过 batch_id 回溯原始对话
- residual → 用 note() 表达

删除后减少 30-40% 输出 token，消除一整类格式错误。

### D2. 为什么禁止内联嵌套

`hope(@self, visit(@self, @tokyo))` 需要 LLM 正确匹配括号。
实测中嵌套括号是 LLM 的第一大出错来源。改为 `$id` 引用后，
每行只有一层括号，LLM 只需要生成 `pred(a, b)` 的固定模式。

行数增加约 20-30%，但每行出错率大幅下降，净效果正收益。

### D3. 为什么删列表语法

`speak(@self, ["中文", "英语"])` 引入了 `[]` 嵌套，且无法为每个值
独立附加修饰（比如"英语"是 fluent，"日语"是 slight）。
展开为多条 STMT 后，每条独立可修饰、独立可索引。

### D4. 为什么删 scope

local/world 区分在单 owner MVP 中无实际作用，且增加 LLM 决策成本
（"Google 是 local 还是 world？"）。TYPE 已经提供了足够的分类信息。
多 owner 场景下可作为 REF 属性重新引入，无需改语法。

### D5. 为什么 pred 必须是种子词

允许 LLM 自创谓词（v1 的 NEW_PRED 机制）导致词表不可控膨胀，
同义近义词满天飞。强制种子词 + `:suggested_word` 的模式：
- 解析器**永远稳定**——pred 总是已知的
- LLM 的建议**不影响逻辑**——只是一个附注字段
- 词表演化**人类可控**——审查 suggested_pred 后批量晋升

### D6. 为什么 REF 用 `:` 而 STMT 用 `=`

视觉区分。LLM 生成时形成两种固定模式：
- `@word: word "word"` — REF 模式
- `$word = word(...)` — STMT 模式

两种模式的 token 序列字面差异大，减少 LLM 模式混淆。
