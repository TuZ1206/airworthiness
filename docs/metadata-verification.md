# 法规来源元数据核验

首次核验：2026-10-13T08:15:27Z；第二轮缓存复核：2026-10-13T09:09:36Z。输入为 `docs/data-quality-report.md` 中的 26 项提示及 189 条来源登记。基线提交：`a835c44a88f52ce589cd848fa5d5da8e72aa12b8`；分支保持 `feat/offline-resource-hall`。

26 项中，25 项已有确定纠错值或差异解释，1 项未解决（HB 7736-2004 缺官方详情）。台账中的 5 组 CAAC 桌面/PHONE 地址已全部确认；另有 2 组取证辅助地址，共 7 组别名。JSON 共 28 条分组发现：12 条覆盖全部提示，9 条补充身份/效力或题名元数据，7 条核验地址别名。新增 M09 纠正 CH08-S007 的题名。

这里的“已解决”不代表已改台账，也不代表通过最终专业审核。结论总表保持 `review_status=pending`；新修正层不改变任何文档的既有审核状态。本任务写集仅为本报告、[metadata-findings.json](../data/verification/metadata-findings.json)、[verification.py](../src/airworthiness/verification.py) 和 [test_verification.py](../tests/test_verification.py)。

## CI 原始缓存复核

首轮缓存复核只读复用 `.cache/ci-acquisition-38367606768/.cache/acquisition`，未再次发起 web 连接。135 份清单及原始字节（134 HTML、1 PDF）逐一重算大小和 SHA-256，均与清单一致。已读取其中与本任务相关的 19 份 HTML，并在 JSON 的 `cache_evidence` 保存来源 URL、采集时间、缓存路径、哈希和附件地址，具体发现通过 `cache_evidence_ids` 关联。

第二轮只读检查 `.cache/ci-acquisition-38368418797/.cache/acquisition` 中与本任务直接相关的 8 份原始文件（4 HTML、4 PDF），重算大小和 SHA-256 均与清单一致，新增证据 C20–C27。设计指南正式 PDF 封面已确认 AC-21-48，解决原提示2、3；CCAR-21 两端修改决定 PDF 字节一致；CH08-S007 扫描封面支持纠正题名。没有声称复核全部242份新缓存或逐页审核附件。HB 检索页的零结果仍不能推导标准不存在。

## 核验口径

已打开并读取相关官方发布页元数据、通知正文、可访问 PDF 的封面和相关生效条款。搜索摘要仅用于定位，未用于认定。长篇技术规定只阅读支持元数据判断的相应位置，不宣称完成全文技术或版式审核。首轮远端 PDF 截图曾超时；本轮按 PDF 技能直接渲染缓存并视觉核对设计指南封面及第6节，同时查看主任务提供的 CH08-S007 官方扫描封面。其余没有实际查看图像的页面不声称完成版式核验。

`publish_date` 默认对应登记 URL 的官方发文日期；通知发布日期、正文下发日、实施日期分别记录。部号、程序/通告文号和印发通知字号不得混为一列含义。无法访问的附件不用于推定编号。JSON 的 `old_values` 按来源编号保留首次核验基线，`verified_value=null` 表示没有足够证据。

## 26 项提示覆盖

下表按输入报告的提示顺序编号，合并同一争议的跨章提示；精确旧值、证据地址、每项时间和理由见 JSON 的同名记录。

| 提示序号 | 发现 | 来源编号 | 字段 | 结论 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | P01 | CH04-S010 | publish_date | 缺官方详情，发布日期留空。 | unresolved |
| 2、3 | P02 | CH02-S001、CH06-S016 | document_code | 正式 PDF 封面编号 AC-21-48；只改 CH06-S016 的缺号占位值。 | verified |
| 4、5 | P03 | CH02-S037、CH05-S012 | document_code | 民航规〔2023〕36号；网页字号栏和附件首页均有依据。 | verified |
| 6、7、8、9、10、11、12 | P04 | CH01-S008、CH03-S001、CH04-S001、CH05-S001、CH07-S001、CH08-S001、CH09-S001 | publish_date | 当前登记来源日期为 2016-03-17；2011-11-07 属早期修订发布。 | verified |
| 13、14、15 | P05 | CH01-S019、CH02-S036、CH05-S008 | title | 官方标题含顿号；标点差异仅解释，不强制统一。 | equivalent_title |
| 16、17 | P06 | CH01-S021、CH06-S010 | title | 官方标题含书名号；标点差异仅解释，不强制统一。 | equivalent_title |
| 18、20 | P07 | CH02-S070、CH08-S008 | publish_date | 通知日 2012-07-02；正文下发/实施日 2012-06-29。 | scope_distinction |
| 19 | P08 | CH02-S071 | publish_date | 英文版日期 2012-06-29 正确。 | scope_distinction |
| 21 | P09 | CH02-S070 | title | 保留发布通知长标题。 | scope_distinction |
| 22 | P10 | CH02-S071 | title | 保留英文版题名和语言标记。 | scope_distinction |
| 23 | P11 | CH08-S008 | title | 现有“符合性方法”题名无本来源支持，应按通知或正文层次修正。 | verified |
| 24、25、26 | P12 | CH03-S007、CH04-S009、CH07-S007 | title | 官方题名是“型号合格审定程序”；历史说明与废止状态另存。 | verified |

## 关键依据与处理建议

### P01 · publish_date

来源：CH04-S010。核验时间：2026-10-13T08:30:58Z。结果：`unresolved`。

已读取 CI 缓存的官方检索页，页面显示相关结果为 0，且没有标准详情。该检索结果不能提供 HB 7736-2004 的发布日期。

确定值：未填（JSON 为 null）。

未解决原因：此前 web 访问失败已由缓存读取补足；当前缺口是该检索页没有对应标准详情或发布公告。零结果不能证明标准不存在。

后续取证：取得准确的官方标准详情页或发布公告后补核，不以其他编号、商业目录或年份推算日期。

[官方证据 1](https://std.samr.gov.cn/search/stdPage?q=HB%207736%202004&tid=)。

### P02 · document_code

来源：CH02-S001、CH06-S016。核验时间：2026-10-13T09:09:36Z。结果：`verified`；执行意图：`corrected`。

正式59页 PDF 封面明确载有编号 AC-21-48、题名设计保证系统建设指南、下发日期2026-09-17；已核对数字文本与封面图像。HTML 的文号空白不能推翻附件的明示编号。

确定值：AC-21-48。CH02-S001 原编号正确；CH06-S016 的“官网未列编号”改为该编号。

附带日期区分：物理第51页（印刷页码47）第6节写2026-09-01生效，已视觉确认。该日早于封面下发日期；这里只分别记录官方原值，不据此推定错字或覆盖 `publish_date=2026-09-17`。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202609/t20260921_231762.html)；[官方证据 2](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202609/P020260921617424013037.pdf)。

### P03 · document_code

来源：CH02-S037、CH05-S012。核验时间：2026-10-13T08:15:27Z。结果：`verified`。

网页字号栏给出民航规〔2023〕36号，PDF 首页的修订印发通知再次载明该号，并署 2023 年 12 月 4 日。

确定值：民航规〔2023〕36号。

CH02-S037 的长标题对应发布通知；CH05-S012 的短标题对应同一 PDF 第2页起的细化要求正文。它们是通知与所附正文关系。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202312/t20231223_222426.html)；[官方证据 2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/202312/P020231223438346814379.pdf)。

### P04 · publish_date

来源：CH01-S008、CH03-S001、CH04-S001、CH05-S001、CH07-S001、CH08-S001、CH09-S001。核验时间：2026-10-13T08:15:27Z。结果：`verified`。

两版 CAAC 网页的发文日期一致为 2016-03-17；官方历史说明指出 2011-11-07 曾颁发修订版，2016 年交通运输部颁布版本与其内容一致；交通运输部正文标明 2016-03-17 公布、2016-04-17 施行。

确定值：2016-03-17。

2011 日期有官方历史依据，但不匹配当前登记的 2016 来源页。不得将两年内容一致解释为两次颁布是同一次事件。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/MHGZ/201606/t20160622_38638.html)；[官方证据 2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/MHGZ/201606/t20160622_38638.html)；[官方证据 3](https://www.caac.gov.cn/ZTZL/RDZT/2021BNWY/GGKF/202107/t20210707_208324.html)；[官方证据 4](https://xxgk.mot.gov.cn/gz/202112/t20211227_3633506.html)。

### P05 · title

来源：CH01-S019、CH02-S036、CH05-S008。核验时间：2026-10-13T08:15:27Z。结果：`equivalent_title`。

官方标题在专用条件后保留顿号。三条记录链接、文号一致，CH05-S008 的差异仅为漏掉这一标点。

确定值：颁发专用条件、批准豁免和做出等效安全水平结论的程序。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202312/t20231223_222428.html)。

### P06 · title

来源：CH01-S021、CH06-S010。核验时间：2026-10-13T08:15:27Z。结果：`equivalent_title`。

官方通知标题使用书名号，正文说明公布的是截至 2024 年底整理的双边适航文件目录，并署 2025 年 2 月 14 日。CH06-S010 仅省略标题书名号。

确定值：关于公布《与我国建立双边适航关系的国家及有关文件目录》的通知。

通知与所附目录是不同文献层次；本项只确认两条通知题名的标点等价。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/ZFGW/202503/t20250314_226931.html)。

### P07 · publish_date

来源：CH02-S070、CH08-S008。核验时间：2026-10-13T08:15:27Z。结果：`scope_distinction`。

通知网页的发文日期和正文落款都是 2012-07-02；其所附咨询通告封面下发日期为 2012-06-29，第4.2条亦规定该日实施。

确定值：2012-07-02。

verified_value 对应登记 URL 的通知发布日期；若条目改以通告正文为对象，应独立保留正文下发日期，不把通知和正文日期强制合并。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8170.html)；[官方证据 2](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/P020151103347114963684.pdf)。

### P08 · publish_date

来源：CH02-S071。核验时间：2026-10-13T08:30:58Z。结果：`scope_distinction`。

官方英文版页发文日期是 2012-06-29，英文 PDF 封面的 Issue Date 和第4.2条相互印证；该值与中文通告下发日期一致，早于通知日期。

确定值：2012-06-29。

保留现有日期；本轮缓存补足原桌面页，其日期与上轮已读官方 PHONE 页面和英文 PDF 一致。

[官方证据 1](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/t20151102_8258.html)；[官方证据 2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/P020151103347328337468.pdf)；[官方证据 3](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8170.html)；[官方证据 4](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/P020151103347114963684.pdf)；[官方证据 5](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8258.html)。

### P09 · title

来源：CH02-S070。核验时间：2026-10-13T08:15:27Z。结果：`scope_distinction`。

登记长标题就是官方发布通知标题；通知明确发布所附 AC-26-AA-2012-01。通告封面有单独的正文题名。

确定值：关于发布咨询通告《运输类飞机持续适航和安全改进及点火源防护符合性指南》的通知。

保留发布通知标题，不与英文版标题强制统一。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8170.html)；[官方证据 2](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/P020151103347114963684.pdf)。

### P10 · title

来源：CH02-S071。核验时间：2026-10-13T08:15:27Z。结果：`scope_distinction`。

官方页明确标识英文版，并与通知互列相关链接；英文 PDF 的编号和下发日期与中文通告一致，属于语言版本关系。

确定值：运输类飞机持续适航和安全改进及点火源防护符合性指南（英文版）。

保留英文版标识；不把该页当作同一 URL 的重复通知，也不宣称中英文附件字节相同。

[官方证据 1](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/t20151102_8258.html)；[官方证据 2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/P020151103347328337468.pdf)；[官方证据 3](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8170.html)。

### P11 · title

来源：CH08-S008。核验时间：2026-10-13T08:15:27Z。结果：`verified`。

该记录与 CH02-S070 指向同一通知；官方通知及中文通告封面均未使用目前登记的符合性方法题名，且现题名遗漏了点火源防护这一部分。

确定值：关于发布咨询通告《运输类飞机持续适航和安全改进及点火源防护符合性指南》的通知。

若后续台账明确以正文为登记对象，可使用 alternative_document_title，并另存通告下发日期 2012-06-29；不是单纯的标点差异。

若改以正文为对象，其题名为《运输类飞机持续适航和安全改进及点火源防护符合性指南》。

[官方证据 1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8170.html)；[官方证据 2](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/P020151103347114963684.pdf)。

### P12 · title

来源：CH03-S007、CH04-S009、CH07-S007。核验时间：2026-10-13T08:30:58Z。结果：`verified`。

桌面页缓存与此前已读官方 PHONE 页均显示型号合格审定程序、AP-21-AA-2023-11R1、2023-12-06 和废止；历史版本属于台账说明。

确定值：型号合格审定程序。

旧版状态继续保留 abolished；本轮已补读桌面 HTML。旧版 PDF 不在本批缓存，尚未核定废止生效日及具体替代条款。

[官方证据 1](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/202312/t20231223_222437.html)；[官方证据 2](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202312/t20231223_222437.html)。

## 补充的身份与效力信息

以下效力只表示访问时官方页面明示的状态；专业适用性审核仍保留。结构化原值与确定值见 M01–M08。

| 发现 | 关联来源 | 已确认信息 | 证据 |
| --- | --- | --- | --- |
| M01 | CH02-S001、CH06-S016 | 题名正确，发布日期2026-09-17，有效；PDF另证编号 AC-21-48、生效日期2026-09-01。 | [证据1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202609/t20260921_231762.html) |
| M02 | CH02-S037、CH05-S012 | 民航规〔2023〕36号包含印发通知和细化要求正文；2023-12-04，有效。 | [证据1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202312/t20231223_222426.html)、[证据2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/202312/P020231223438346814379.pdf) |
| M03 | CH01-S008、CH03-S001、CH04-S001、CH05-S001、CH07-S001、CH08-S001、CH09-S001 | CCAR-25-R4；交通运输部令2016年第19号；官方目录标有效。详情页效力栏为空，不能独立推出有效。 | [证据1](https://www.caac.gov.cn/XXGK/XXGK/MHGZ/201606/t20160622_38638.html)、[证据2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/MHGZ/201606/t20160622_38638.html)、[证据3](https://xxgk.mot.gov.cn/gz/202112/t20211227_3633506.html)、[证据4](https://www.caac.gov.cn/was5/web/search?channelid=269689&divShow=wenhao&fl=13&orderby=-fabuDate&outlinepage=7&page=13&perpage=10&selST=All&selYouxiao=All&was_custom_expr=+PARENTID%3D%2713%27+or+CLASSINFOID%3D%2713%27+) |
| M04 | CH01-S019、CH02-S036、CH05-S008 | AP-21-AA-2023-17；民航规〔2023〕38号；2023-12-06，有效。 | [证据1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202312/t20231223_222428.html) |
| M05 | CH01-S021、CH06-S010 | 民航适函〔2025〕25号；2025-02-14，有效。 | [证据1](https://www.caac.gov.cn/XXGK/XXGK/ZFGW/202503/t20250314_226931.html) |
| M06 | CH02-S070、CH02-S071、CH08-S008 | 中英文均为 AC-26-AA-2012-01；通知页和英文页均标有效。 | [证据1](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8170.html)、[证据2](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/t20151102_8258.html)、[证据3](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/P020151103347114963684.pdf)、[证据4](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/P020151103347328337468.pdf) |
| M07 | CH03-S007、CH04-S009、CH07-S007 | AP-21-AA-2023-11R1；民航规〔2023〕46号；2023-12-06，废止。同名新版 AP-21-11R2 页面标 2026-06-25、有效，不能合并版本。 | [证据1](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/202312/t20231223_222437.html)、[证据2](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202607/t20260701_231208.html) |
| M08 | CH04-S010 | HB 7736-2004 的题名、编号真实性及状态均未取得官方详情；保持 unknown。 | [证据1](https://std.samr.gov.cn/search/stdPage?q=HB%207736%202004&tid=) |

## CAAC 桌面 / PHONE 地址别名

只将通过官方网页读取或官方原始 HTML 缓存实际核对两端元数据的地址记作可证实别名。除 A05 指定 PDF 对完成二进制哈希比对外，其余别名仅确认官方展示记录；同尾号不能单独构成验证。以下 canonical_url 是本地建议保留的桌面登记地址，不表示网站提供了 canonical 标签或重定向。

| 发现 | 文件 | 桌面地址 | PHONE 地址 | 双端核验结果 |
| --- | --- | --- | --- | --- |
| A01 | 运输类飞机适航标准（CCAR-25-R4） | [桌面](https://www.caac.gov.cn/XXGK/XXGK/MHGZ/201606/t20160622_38638.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/MHGZ/201606/t20160622_38638.html) | 已确认题名、编号、日期和附件名称对应同一发布记录 |
| A02 | 复合材料结构制造质量体系要求指南（AC-21-AA-2017-39） | [桌面](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201801/t20180124_48751.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201801/t20180124_48751.html) | 已确认题名、编号、日期和附件名称对应同一发布记录 |
| A03 | 航空产品设计更改审定基础的确定程序（AP-21-AA-2014-36） | [桌面](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8262.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/t20151102_8262.html) | 已确认题名、编号、日期和附件名称对应同一发布记录 |
| A04 | 运输类飞机持续结构完整性大纲（AC-25-AA-2022-01） | [桌面](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202207/t20220708_214043.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/202207/t20220708_214043.html) | 已确认题名、编号、日期和附件名称对应同一发布记录 |
| A05 | 交通运输部关于修改《民用航空产品和零部件合格审定规定》的决定（CCAR-21-R5） | [桌面](https://www.caac.gov.cn/XXGK/XXGK/MHGZ/202403/t20240313_223201.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/MHGZ/202403/t20240313_223201.html) | 双端元数据、通知正文及指定 PDF 字节一致 |

A05 的双端原始 HTML 已确认修改决定题名、交通运输部令2024年第5号、CCAR-21-R5、2024-02-18 及有效状态；两端通知正文均说明自2024-04-01施行，并指向同尾名的 P020240313332916593770.pdf。新增缓存比对表明两份 PDF 都为438100字节，重算 SHA-256 同为 `51b8f078c64d43750102b05404f901df698b2c77944a74537e86e6c63d119de3`。台账使用规定本体题名，应保留修改决定与合并正文的关系。主任务负责 CCAR-21 全文，本任务只比对既有附件字节，没有生成、改写或共享正文。

另有 2 组取证辅助别名，本轮用桌面 HTML 缓存与上轮已读取的 PHONE 页确认：

| 发现 | 文件 | 桌面 | PHONE | 结果 |
| --- | --- | --- | --- | --- |
| A06 | 型号合格审定程序 | [桌面](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/202312/t20231223_222437.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/202312/t20231223_222437.html) | equivalent_url |
| A07 | 运输类飞机持续适航和安全改进及点火源防护符合性指南（英文版） | [桌面](https://www.caac.gov.cn/XXGK/XXGK/GFXWJ/201511/t20151102_8258.html) | [PHONE](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/t20151102_8258.html) | equivalent_url |

这2组单独列出；与台账原有5组相加，共7组已证实的官方展示地址别名。其中仅 A05 的上述 PDF 对做过字节一致性认定；修正层对全部别名都只记录，不据此复用正文。

## 访问限制与未完成取证

- HB 标准检索入口已由缓存恢复读取，但只有零结果，没有标准详情；不能据此认定标准不存在、已废止或推测发布日期。
- 《设计保证系统建设指南》正式 PDF 已由第二轮缓存恢复，封面编号已确认，前轮相关访问限制不再阻碍编号核验。
- 民航规〔2023〕36号桌面 PDF 超时，已通过官方 PHONE 附件读取通知首页和正文题名。
- CCAR-25 附件两端超时，日期使用 CAAC 双端 HTML、官方历史说明及交通运输部公布说明交叉确认。
- 专用条件程序附件复取失败，标题和其他元数据结论依据其完整官方发布页；旧型号程序的废止信息已由官方桌面 HTML 缓存和 PHONE 页共同支持。没有核定旧程序的废止生效日或具体替代条款。
- AC-26 英文版桌面页已由缓存补读，其元数据与官方 PHONE 页及英文 PDF 一致；中文 PDF 的封面和第4.2条也已读取。
- 本机 HTTPS 请求出现 TLS EOF；远端 web 能读取部分官方 HTML/PDF。早期远端 PDF 截图失败，本轮指定两份缓存 PDF 的封面已本地视觉核对；未修改代理、网络设置或受控文件。

此前访问失败及本轮缓存恢复路径逐项保存在 JSON 的 `access_limitations`；`first_check_result` 保留前轮状态。目前仅提示1仍未解决，应保留待核状态，不用虚构值消除提示。其他附件的早期访问失败仅记录取证过程，不等于在最新缓存中仍不可获得。

## M09 · CH08-S007 题名纠错

台账登记“持续适航文件”，文号为 AC-25.1529-1；[完整官方 PHONE 页面](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/t20151102_8386.html) 显示名称和附件标签均为“审定维修要求”、同一文号、1996-09-18、有效。已视觉查看[21页扫描 PDF](https://www.caac.gov.cn/PHONE/XXGK_17/XXGK/GFXWJ/201511/P020151103347692049750.pdf) 第1页，封面同样明确显示该题名、编号和生效日期。PDF 无文字层不是无正文。

因此 M09 为 `verified + corrected`，题名改为“审定维修要求”，编号/日期/状态不变。最初的 `unresolved_source_identity` 疑点由封面证据解除；它不应继续被误报为未决。但这不证明旧上传摘录与扫描全文逐字对应，仍不能仅同 URL 就共享正文。CH05-S013 的扫描全文及 OCR 由主任务处理，本修正层不改写两份 PDF 或机械提取内容。

## 可用修正层接口（供接入方）

```python
from airworthiness.verification import apply_metadata

# documents: load_inputs 返回的原始文档字典列表；issues: 原始待核提示
resolved_issues, unresolved_issues = apply_metadata(documents, issues, root)
# documents 的字典已就地叠加修正；展示两组 issues，勿丢弃 resolved_issues。
```

`root` 是仓库根目录（字符串或 Path）。调用只读 `data/verification/metadata-findings.json`，无联网或磁盘写入。建议在原始元数据生成提示之后、目录/API持久化之前调用；原始采集绑定检查应仍以 CSV 值为准，不用修正后的题名/日期重新判定采集成功。此模块不接管 ingest/catalog/manifest，也不阻止或执行其现有正文共享逻辑。

### 执行白名单与字段

schema 1.2 为每条 finding 新增 `resolution` 和 `source_urls[source_id]`。只有 `result="verified"` 且 `resolution="corrected"` 的明确标量值允许应用。还必须有非空官方 gov.cn 证据 URL、精确短引文（最多25字符）或 paraphrase、有时区的 checked_at、匹配的旧值及精确来源 URL；日期需为有效 YYYY-MM-DD。未知 schema、损坏文件、过期绑定或互相冲突的确定值均不执行修正，提示保留未解决。

| finding.field | 文档实际字段 | 可消解 issue.kind |
| --- | --- | --- |
| title | title | title_variation |
| date / publish_date | publish_date | date_variation、missing_date |
| code / document_code | document_code | code_conflict |

`metadata` 对象、`url_alias`、document_status、review_status、body、URL、哈希、采集及正文溯源一律不在写入白名单。未知 issue.kind（包括 stale_acquisition、status_variation）原样保留。差异合理时用 `equivalent_title/scope_distinction + explained`，只消解匹配字段的提示，不统一题名/日期。补充证据与别名使用 `recorded`；`verified` 单独出现不授权修正。未来若 finding 明确为 `unresolved_source_identity`，该 source_id 的所有自动修正和提示消解都被拦截，但模块仍不擅自撤回或替换正文，接入方需处理正文隔离。

### 文档与返回值

- 每个文档有 `original_metadata`：首次调用前的 title、document_code、publish_date、document_status、url、review_status；已有旧值不覆盖。
- 每个文档有 `metadata_verification` 数组；无相关证据时为空。记录保留 finding_id、单数 source_id、标准化 field、result、resolution、verified_value、evidence_url、evidence、checked_at、日期层次/附件哈希等解释。
- 运行结果在证据的 `application` 中：corrected、already_matches、explained、confirmed、recorded、unresolved 或 blocked。仅 corrected 且与 original_metadata 不同时 `applied=true`；拒绝原因见 block_reason。重复调用不重复修正或覆盖旧值。
- resolved_issues 为原提示的副本，新增 `resolution`、`finding_ids`、`evidence=[上述依据]`。组内本来正确的记录也可消解对应冲突提示，但 `applied=false`。
- unresolved_issues 保留原提示对象、字段和顺序；输入 issues 不被修改。没有原提示的新增 M09 仍会叠加题名修正，并通过文档 metadata_verification 展示，不凭空生成提示。
- review_status 原样保留；本次数据均 pending，最终专业审核未完成。

### 本次精确改动集

| 来源编号 | 字段 | 旧值 | 修正值 | 依据 |
| --- | --- | --- | --- | --- |
| CH06-S016 | document_code | 官网未列编号 | AC-21-48 | P02 |
| CH02-S037 | document_code | 官网未标注文号 | 民航规〔2023〕36号 | P03 |
| CH03-S001、CH08-S001、CH09-S001 | publish_date | 2011-11-07 | 2016-03-17 | P04 |
| CH08-S008 | title | 运输类飞机的持续适航和安全改进规定符合性方法 | 关于发布咨询通告《运输类飞机持续适航和安全改进及点火源防护符合性指南》的通知 | P11 |
| CH03-S007 | title | 型号合格审定程序历史版本 | 型号合格审定程序 | P12 |
| CH08-S007 | title | 持续适航文件 | 审定维修要求 | M09 |

共8个来源的8个字段。原26条提示中，15条按纠错结论消解（含组内原值正确者）、10条按合理差异解释消解、1条仍未解决。此统计不等于25个字段都被修改。

## 交付检查

按 TDD 技能先新增测试并观察修正层缺失造成的失败，再实现；补充畸形决策类型测试也先失败后修复。16项独立测试覆盖白名单、字段映射、绑定过期、证据缺失/冲突、合理差异、别名只读、审核状态不变、幂等及真实189条来源的精确8字段改动。

按 verification-before-completion 流程在交付前重新运行测试，并检查 JSON 可解析、全部26项提示恰好覆盖一次、来源编号存在、旧值与基线一致、确定值/统计可重算、新增缓存证据大小和哈希匹配。最终专业审核留给用户；未切分支、commit、push。

全仓回归快照：`python -X utf8 -m unittest discover -s tests -v` 运行181项，179项通过、2项失败（161秒）。本模块16项及定位接入测试通过。按 systematic-debugging 检查失败链，均为旧断言期待新功能之前的行为：

- `tests/test_library.py:81` 仍要求 CH03-S001 的 date_variation 留在 `quality.issues`；P04 已按官方证据解决此提示，应由主任务调整断言检查已解决记录及保留的旧日期。
- `tests/test_library.py:64` 仍要求所有术语只链接 source、不带 fragment；定位层现在返回如 `#clause-3` 的有依据锚点，应由定位任务更新兼容性断言。

未修改上述测试或接入代码。接入检查时另见 `ingest.py` 将第一个返回值赋给 `_resolved_issues`，`catalog.quality` 则从文档证据生成 `resolved_metadata`。该展示已有依据，但不等同于保存本接口返回的原提示副本；如果 API 需要原提示 kind/message，接入方应单独持久化并返回 `resolved_issues`。`data/verification/standards-access.json` 及其缺口理由不在本任务处理范围。
