# S1.1 分层流程（仅定性）

当前完成阶段：独立 PDF 解析。检索、向量索引及评分尚未实现。

## 环境与运行

使用 Python 3，安装本目录 requirements.txt 中的第三方依赖。所有项目源码均在本目录 pdf_parser 内，未导入其他项目目录代码。Docling CLI 是安装的第三方工具，默认从 PATH 查找；没有硬编码其他项目的虚拟环境。

```sh
cd ESG-分层agent
python3 parse_pdf.py parse /path/report.pdf --output outputs/report
# 可选：复用与该 PDF 对应的 Docling 原始 JSON
python3 parse_pdf.py parse /path/report.pdf --docling-json /path/report.json --output outputs/report
python3 tests/check_pdf_output.py outputs/report
```

默认禁用 OCR，不做固定字数切分，不调用大模型，不自动降级其他解析器。复用外部 JSON 时调用者须确认与 PDF 一致；原始 Docling JSON 应随运行资料归档。

## 输出

- `retrieval_chunks.jsonl`：正文自然段、列表、表格块、脚注、图内文字。稳定ID、文件哈希、物理页、bbox、源块ID、文本哈希、前后chunk、同页标题候选。
- 表格保留 `table_rows` 与可取得的 `raw_table`（原始单元格、表头标识、跨度、定位等），不是大模型重写。
- `note_candidates` 仅表示同页脚注候选，`linked_note_ids` 默认空；不能把候选当确认归属。
- `table_continuation_candidates` 仅为下一页表格候选；不自动合并跨页表。表头、单位、注释仍需原件核验。
- `paragraphs.jsonl`：自然段及语义块的完整解析记录（保留旧ID）；新增辅助chunk见 retrieval_chunks。
- `blocks.jsonl`、`tables.jsonl`、`figures.jsonl`、`visual_texts.jsonl`：底层审计资料。
- `page_quality.json`：逐页低文本量提示；不是完整解析质量判定，不证明扫描页或覆盖完整。
- `source.json`：来源登记占位。文件性质、年度、URL、发布主体需材料登记阶段填写；不从文件名推断。
- `parse_manifest.json`：文件哈希、解析参数与版本、产物清单。

所有 `quote_match` 初始为 null，覆盖状态为 not_reviewed；解析成功不等于原文已核验或检索完成。印刷页码未知留空。章节是原解析器的近似章节标签，并非可靠多层目录；前后chunk是阅读上下文候选，检索阶段仍需检查章节边界。

## 验证样本

validation/pdf_sample 使用已有69页实际PDF及其Docling JSON重建，未调用外部项目源码，未重新运行Docling模型。样本是技术验证，不是新流程的正式企业证据登记。原解析算法移植自本仓库既有自然段解析器；本目录代码独立维护。

## 整份PDF覆盖要求

输入必须为完整PDF，不按员工主题预筛页。Docling页号必须完整覆盖物理页1至末页，否则失败。目录与封面不再按页面排除；附录、表格和脚注均处理。正文仍按完整自然段生成多个chunk，不把整份PDF作为单个chunk。低文本量页面保留质量问题，不能仅凭页号齐全宣称内容完整。

## 超长自然段与检索子块

`retrieval_chunks.jsonl` 始终保存完整自然段。新增 `retrieval_units.jsonl` 供后续索引使用：短段落一对一；超长段落生成多个派生子块，保留 parent_chunk_id、字符起止区间（左闭右开）、序号和总数。主段落不修改，子块拼接可完整恢复原文，无截断、无重叠。

默认按包含章节前缀在内的8000 UTF-8字节保守预算切分，不将其声称为实际token计数。预算集中配置于 pdf_parser/retrieval_units.py；模型或接口限制改变时须复核。极长章节前缀不放入向量输入，但原始元数据仍完整保留。后续召回需按 parent_chunk_id 恢复完整段落，LLM超长上下文分批处理属于后续阶段，本次未实现。

验证：tests/test_retrieval_units.py 检查长中文及emoji原文恢复、偏移、预算、稳定ID及短段不拆分。

## 材料登记与来源分层

```sh
python3 register_materials.py config/materials.json --output outputs/registry
python3 tests/test_material_registry.py
```

输入支持JSON数组或JSONL，字段样例见 config/materials.example.json。相对路径相对输入文件所在目录。企业代码必须是字符串；文件必须存在，哈希不一致则失败。未知年度、文件类型不从文件名或域名推断，记录 pending_review。

文件性质映射L1：esg/sustainability/csr；L2：annual/financial_statement/financial_notes；L3：thematic_report/governance/policy/announcement；L4：official_regulatory_notice/official_judicial_notice。official_verified 只记录登记者的核验结果，程序不访问网站核实来源。材料登记成功不表示检索范围完整。

同企业同哈希镜像合并并保留地址、路径及镜像登记记录；内容不同的修订版保留独立source_id，supersedes_source_id 指向旧版。版本或类型矛盾直接拒绝；被更正材料不在清单时标记待核验。

输出 sources.jsonl、summary.json、linked/<source_id>/ 下的关联chunk和检索单元。source_id 为企业代码＋文件哈希，原chunk编号及字符区间不变。原始解析产物不修改；注册前验证解析manifest哈希及每条记录来源。后续必须以(company_id, source_id, chunk_id)识别证据，避免多企业共用同一PDF时混用。

validation/registry_sample 是接口验证，缺失的企业名称、来源和年度保持待核验，不能作为正式证据登记。

## BM25与向量索引

```sh
python3 build_index.py --registry outputs/registry --output outputs/index --env-file /path/to/.env
python3 tests/test_index.py
```

环境变量或显式env文件提供 EMBEDDING_MODEL、EMBEDDING_BASE_URL、EMBEDDING_API_KEY；环境变量优先。代码不硬编码其他目录配置路径，不保存密钥。使用API，1024维float32，归一化后精确余弦点积；每批20条、最多3次尝试。缓存键包含服务地址、模型、维度和输入文本。正式使用沿用text-embedding-3-small。

仅metadata_status=registered且层级明确的材料进入索引；不合格材料在build_summary.json列出，不自动补猜。按企业/L1—L4分别输出embeddings.npy、row_map.jsonl、units.jsonl、chunks.jsonl、sources.jsonl、bm25_tokens.jsonl、manifest.json。BM25分词和k1=1.5、b=0.75沿用基线。索引检索对象为派生unit，通过parent_chunk_id恢复完整自然段。

当前检索调度、混合排序和评分尚未实现。没有正式登记的材料时，不会生成正式材料索引。validation/api_index_smoke仅使用三条技术样例验证API，不是企业证据。

### 随机10家实际索引运行

runs/random10_20261127/selection.json 固定保存20家总体及种子20261127抽中的10家。该轮仅覆盖2025年度ESG主报告的L1索引，其余材料列于 remaining_materials_inventory.json，不代表其他层级已核查。输入PDF及Docling JSON已复制至本轮materials，独立解析器重新构建chunk；不导入历史项目代码。材料类型及官方来源依据继承的历史材料登记记录，未重新联网验证。

批量embedding使用4并发、每批20条。用户已明确授权向api.hkubs.ai发送所选10份公开报告的派生文本。缓存可续建；manifest中的usage仅记录本次进程新请求，不包括过往进程及缓存的历史计费。`vector_ready=false` 表示仅BM25，不能当向量索引使用。

```sh
python3 tests/check_vector_indexes.py runs/random10_20261127/index
```

该检查核验全部向量维度、数值、归一化、行号映射及父段落偏移，并抽样核验向量自身相似度。通过不等同于已评估语义召回质量。

## 补充材料分类、解析与分层索引

`scripts/prepare_layered_index.py` 从已落地的 material_catalog.jsonl 生成 layered/classification_plan.json。保留排除与待核实原因：2024报告备查、明显非员工议题、导航入口、主题未明确的政策及扫描待核实材料不自动混入当前评价语料。未知政策生效时间保留 evidence_issues，登记/入库不表示2025年适用或引文已核验。

PDF仍由本目录解析器处理，OCR默认关闭。已有Docling JSON仅作为数据复制至本目录使用；新PDF使用第三方Docling运行时。`docling_cli.py` 提供本目录第三方库入口，可通过 --docling-python 显式指定装有Docling的Python，不导入其他项目业务源码。

HTML由本目录 html_parser 解析，保留段落、表格、章节及元素顺序，剔除语义nav/header/footer和脚本；原始快照完整保留。复杂网页结构仍需核验，HTML抽取不等同于浏览器渲染覆盖。

政策没有报告年度不阻止材料登记，但生效期间不自动推定。法院扫描件及其OCR副本暂不进入API向量索引，也不用于自动评分。

```sh
python3 scripts/prepare_layered_index.py --plan-only
python3 scripts/prepare_layered_index.py --docling docling_cli.py --docling-python /path/to/python --workers 3
python3 tests/check_layered_parses.py runs/random10_20261127/layered
```

## 索引完成后自动进入L1试跑

scripts/start_next_after_index.py 等待 layered/completion_status.json 为 completed 后，仅为翰森03692执行25组L1试跑，停在结构化候选和缺项判断，不评分、不自动扩展其他9家。状态见 runs/random10_20261127/l1_pilot_03692/completion_status.json；失败写日志，不静默跳过。

检索使用RAG3.0本地混合算法：BM25/向量各Top150、保护各通道Top10、保留50、每指标首轮18个去重父段。查询由qwen3.8-max一次生成并冻结；原文取证与缺项在同一调用返回，减少重复输入。LLM使用显式env配置的DashScope接口，不在代码存放密钥。

证据卡保留quote/source/location/period/scope/relevance。仅确认引文匹配解析文本时 parsed_text_match=true，PDF原件未核验仍quote_match=null；全部首轮记录search_complete=false、pending_review。长段按输入预算分批且保留父段和字符区间；多个批次仍不足时保留cross_batch_joint_assessment_required标记，不能冒充已完成全文核查。context的资料截止日尚未指定，保留待确认。

当前模型已按用户要求切换为 qwen3.8-flash，后续查询生成和证据/缺项判定统一使用Flash。原Max试跑结果保留；Flash结果单独保存到 runs/random10_20261127/l1_pilot_03692_flash。embedding模型不变。

## 已授权5家公司完整定性流程

入口 `run_full5.py`，守护入口 `scripts/supervise_full5.py`。固定随机样本：03692、01801、02269、01177、06185。模型统一qwen3.8-flash；规则全文及哈希、索引语料版本、代码版本随运行保存。

流程：逐组RAG3.0召回→必要上下文→结构化取证→综合缺项→最多两条互补查询→未解决组进入下一层。L3官网与交易所分阶段；仍缺项时发现并打开官方补充原件。4项严重事项在普通来源结束后独立核查，不因正面证据而跳过。跨指标事实冲突另行审查。

搜索使用独立公开Bing RSS通道定位链接（Flash联网接口验证返回错误）。搜索摘要、模型联网答案不作证据；仅允许官方域名及已登记企业域名的HTTPS原件。链接打不开、扫描未核验、主体关系不明等保留pending_review。新下载PDF先作带物理页定位的辅助原文流，不冒充自然段解析产物。所有派生引文仍须与原件文字匹配；表格和版式引文匹配失败留待视觉核验。

评分逐组0/100/null，程序独立约束待核验状态及100分引用。5个定性小分等权计算，基础分与严重事项后的最终分分开保存；独立核查未决时受影响最终分留空。不计算定量项和完整S1.1总分。程序执行completed不表示全部项目verified。

持久化：每批模型请求按模型/提示词/输入哈希缓存；每层有覆盖及候选检查点；每企业最多3次恢复，监督脚本最多3轮，成功企业与调用不重复收费请求。永久错误保留日志，不伪造成功。结果位于 runs/full5_20261127，completion_status.json 为总状态，逐企业有 retrieval_result.json、scores.json、errors.log，最终有结果汇总.md。

原文核验补充：对解析器做过的NFKC规范化，程序通过字符偏移映射恢复PDF原始连续字符，再确认匹配；不删除标点、不猜词，恢复前的 parsed_quote 单独保留。表格只在PDF本地表格识别结果可重建相同单元格序列时标记 native_pdf_table_cells_match，且 quote_format=native_table_rows；其余表格或版式问题仍待视觉核验。

证据类型校验修复：不再将非法类型自动转为unclassified。仅将出错条目的原标签、引文、期间及范围交回Flash定向纠正，只允许policy/mechanism/action/result/plan/boundary中的一个；原文与其他字段不改。模型纠正通过校验后才继续，保留kind_raw与纠正说明。已收到的原始响应可直接恢复并修复字段，不必重发整批取证请求。

判定保护修正：按模型明确选择的最小充分已核实证据链判断；冗余补充证据的未核验或已排除无效引文保留诊断，不单独推翻独立成立的支撑链。必要证据不明及事实冲突仍pending。E5/T5/W5确认充分必须返回actual_event，指出当期实际发生事实；E5仅无补偿支付不得成立。修正前结果保存在 runs/full5_20261127/before_decisive_fix。

联网检索修正：公开RSS检索实测返回无关链接，已弃用；不再将它视为L4核查完成的依据。当前 fullflow.web.search 写入search_requests，由连接的检索工具执行并回填真实来源，再由本地程序下载官方原件。未收到工具结果不会宣布查完，超时保留pending_review。旧RSS记录仅用于错误诊断。

## 取消全文兜底扫描

普通分层流程仅向LLM提交RAG候选、相邻上下文及最多两轮补充查询候选，不再逐批读取本层全部文本。联网新原件也仅提交BM25定位的最多18个候选块。coverage标记retrieval_only、indexed_content_reviewed=false；完成各层候选检索不等于全文覆盖，未找到充分证据的组保留pending_review，不能据此确认缺披露并判0。已有充分且核验通过的证据仍可正常采用。历史运行结果不改写。

## 候选去重与增量判断

补查按目标组、source_id及chunk_id排除该组已读的父段落（包括首轮相邻上下文）；其他组读过不冒充本组已读。每轮补查后重新判断，只让仍不充分或有冲突的组进入下一轮。缺项判断按目标规则、相关证据及问题记录计算指纹，输入不变时复用本次运行内判断，有新证据、核验状态或问题变化时仅重判受影响组。历史API缓存及运行结果不改写。

## 进一步减少无效模型输入

同轮补查将各组新增候选按(source_id, chunk_id)合并，统一取证并关联参与目标，避免共享原文逐组重复发送；实际提交的段落按参与组记录已读。评分仅发送通用证据要求、判分顺序和本指标定性规则，雇佣及薪酬的A/B定量规则不发送，权重汇总仍由程序执行。缺少L4索引且没有案件原文时直接返回pending_review，扫描线索和覆盖问题仍保留。跨指标证据少于两条时跳过模型冲突检查并记录跳过原因。
