# Telegram alerts

The alert worker posts to a group/channel when recent buyer/seller pressure changes sharply.

## Example dump alert

```text
🚨 SOL dump warning
Net buyers: -8
Net value flow: -$3,200,000
Current value: $8,400,000 long / $5,900,000 short
Signal: -0.31 (Medium)
```

## Example accumulation alert

```text
🟢 HYPE accumulation alert
Net buyers: +7
Net value flow: +$2,100,000
Current value: $35,600,000 long / $15,800,000 short
Signal: +0.43 (High)
```

## Recommended launch settings

```text
ALERT_MIN_NET_BUYERS=5
ALERT_MIN_NET_VALUE_FLOW_USD=1000000
ALERT_COOLDOWN_MINUTES=60
```

Start conservative. Customers hate spam.
