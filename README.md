# 个人生活规划

徐州个人居所决策系统，以独居舒适、商业收入和现金安全为目标，不以房产投资收益为目标。

- `property_goal.md`：需求、区域初筛、证据来源、成交分析、评分规则、资金计划和历史。
- `templates/property_input.json`：单套房源录入模板，未知值保留null。
- `templates/transactions.csv`：挂牌与成交分开记录的数据表头。
- `tools/score_property.py`：有证据才计分，硬门槛优先，未知项限制推荐等级。

运行（Python 3标准库，无额外依赖）：

```sh
python3 tools/score_property.py templates/property_input.json
python3 -m unittest discover -s tests -v
```

评分不是验房或自动购买工具。评分与资金门槛分别评估，实测和产权查验缺一不可。

公开范围：本人已于2026-09-27确认完整计划可以公开同步，包括目标文件中的资产、教育与收入规划。此确认不包括未来新增的原始截图、账单、财务凭证或联系方式，这些内容不得直接提交。
