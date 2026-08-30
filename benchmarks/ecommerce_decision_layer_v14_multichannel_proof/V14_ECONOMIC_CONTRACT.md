# Exergi V14 economic contract

Primary outcome: incremental contribution profit per eligible customer versus BAU, in synthetic USD.

`net_revenue = gross_revenue - discounts - refunds`

`contribution_profit = net_revenue + shipping_revenue - COGS - payment_fees - shipping_cost - shipping_subsidy - fulfilment_cost - return_shipping_cost - restocking_loss - channel_cost - switching_cost - other_variable_cost`

Every component has timestamp, unit, allocation rule, maturity and missingness semantics. COGS, payment,
fulfilment, shipping, subsidy and channel cost are critical. A missing critical cost returns
`DATA_NOT_READY`; it is never zero-filled.

The materiality floor is frozen as the maximum of 1% of mature BAU contribution profit per eligible
customer, direct action cost, switching cost and the family minimum commercial amount. Revenue-positive
but profit-negative decisions are harmful regardless of conversion.
