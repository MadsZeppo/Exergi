# Economics Policy V1

V1 accounting uses:

```text
Net Item Sales = Gross Item Sales - Line Discounts - Refunds

Contribution Profit = Net Item Sales
                    + Shipping Revenue
                    - COGS
                    - Merchant Shipping Cost
                    - Variable Campaign Cost
                    - Payment Processing Cost
```

Source fields already net of a component must not subtract that component again. Merchant-specific return timing and COGS recovery require a frozen `EconomicsPolicy` before a real experiment.

If any required variable cost is missing, contribution profit is `ECONOMICS_NOT_IDENTIFIED`; the product may report net sales/customer but cannot relabel it profit.
