# Exergi V14 action and disposition contract

Frozen actions: BAU/no action, email reminder, email 10% discount, SMS reminder, SMS 10% discount,
free-shipping offer, paid retargeting, onsite personalization, email plus retargeting and suppression/do
not contact.

Frozen product dispositions: `DO`, `TEST`, `AVOID`, `NOT_ENOUGH_EVIDENCE`. The last executes BAU.

Actions fail closed when consent, channel, frequency cap, suppression, inventory, critical cost, known
propensity, conditional support, budget or unresolved prior exposure is invalid. Suppression is a real
action for customers where contact has expected harm; it has no invented positive direct revenue effect.
