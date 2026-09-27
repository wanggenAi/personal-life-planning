# 个人生活规划

徐州个人居所决策系统，以独居舒适、商业收入和现金安全为目标，不以房产投资收益为目标。

- `property_goal.md`：需求、区域初筛、证据来源、成交分析、评分规则、资金计划和历史。
- `templates/property_input.json`：单套房源录入模板，未知值保留null。
- `templates/transactions.csv`：挂牌与成交分开记录的数据表头。
- `tools/score_property.py`：有证据才计分，硬门槛优先，未知项限制推荐等级。
- `property_discovery/`：公开挂牌发现，40-60平方米、最低价不限、最高50万元；访问失败明确记录。
- `candidate_properties.md`：最近一次发现报告，未知条件不冒充已核验。
- `property_discovery/acoustic_investigations.md`：具体房源六维工程证据、风险与核验方法。
- `property_discovery/acoustic_reference.md`：声学规范版本、指标与测量边界；未完成的官方版本核验单列。
- `property_discovery/third_ring_review.md`：V4三环道路几何、坐标口径及逐小区初核；不是具体房源测绘认定。

运行（Python 3标准库，无额外依赖）：

```sh
python3 tools/score_property.py templates/property_input.json
python3 -m unittest discover -s tests -v
```

评分不是验房或自动购买工具。评分与资金门槛分别评估，实测和产权查验缺一不可。

公开范围：本人已于2026-09-27确认完整计划可以公开同步，包括目标文件中的资产、教育与收入规划。此确认不包括未来新增的原始截图、账单、财务凭证或联系方式，这些内容不得直接提交。
