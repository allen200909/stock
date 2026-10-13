# A-share Execution Layer

## Principle

The VLR indicator is a **market-structure factor**. It should describe what happened even when the event itself was not tradable.

Execution filters are therefore applied after the raw signal:

```text
Raw VLR event
    +
A-share execution constraints
    =
Executable research candidate
```

Do not delete genuine liquidity events from the raw factor history merely because they were unbuyable.

## Long-only mapping

For the current A-share workflow:

- VU / EU / ABU: long-side research signals;
- VD / ED / ABD: risk, deterioration, exit or warning signals;
- downward signals are not short-sale instructions.

## Filters to model in research

### 1. Price-limit executability

Historical rules vary by:

- main board;
- ChiNext;
- STAR Market;
- Beijing Stock Exchange;
- ST status;
- IPO/no-limit transition periods;
- rule changes over time.

A production backtest should use point-in-time price-limit rules, not one hard-coded percentage for all dates.

### 2. One-price limit bars

One-price limit-up bars can be valid liquidity-vacuum observations, but generally cannot be treated as ordinary executable entries.

Track:

- RAW_SIGNAL = 1
- EXECUTABLE = 0

rather than deleting the event.

### 3. T+1

Signal at T close implies entry no earlier than T+1.

Do not use T close fills for a daily close-confirmed selector.

### 4. ST and special-treatment stocks

For the default executable universe, exclude ST/*ST unless a separate study explicitly targets them.

### 5. Listing age

Recommended baseline executable-universe requirement:

- at least 250 trading days since listing.

The raw indicator itself may still be calculated earlier once warm-up is available.

### 6. Liquidity

Initial research threshold:

```text
MA(AMOUNT,20) >= 50,000,000 CNY
```

This is a starting research threshold, not a validated optimum.

Also test higher thresholds such as 100 million CNY for capacity robustness.

### 7. Suspensions / resumptions

Resumption after a long suspension can create abnormal gap and volume behavior.

Research data should tag resumption windows separately. Do not assume a formula based only on adjacent K-bars fully captures calendar gaps.

## TDX implementation note

Board/ST price-limit detection through CODELIKE/NAMELIKE and historical rule logic must be validated on the user's TongDaXin installation before being promoted to a canonical formula.

For that reason, this repository keeps the baseline indicator independent from a hard-coded execution formula and treats the execution layer as a research specification first.

