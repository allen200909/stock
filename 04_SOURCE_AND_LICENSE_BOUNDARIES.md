# 参考代码与许可边界

- `reference/third_party/Zeiierman_LTF_Volume_Microburst_Bubbles.pine` 是用户提供的 Zeiierman Pine v6 参考代码，文件头声明 **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International**。其版权不因本任务而转为项目根仓库的 Apache-2.0。
- Zeiierman 参考脚本仅用于研究概念与独立对照；禁止把它逐行转译、复制函数结构/注释/视觉呈现到 Apache 许可的 MBV 项目中。采用独立于脚本表达形式的 RFC 数学定义。
- `reference/vlr_verify/` 提供从 `allen200909/stock` 现有 `projects/tdx-volume-liquidity-residual/verify/` 代码读取的 B0 研究实现和部分辅助模块。代码仍有真实 TDX 逐K验证缺口。为便于 Carbon 离线集成，保持**只读快照**，不修改现有回归公式。
- 该 GitHub 项目整体以 Apache-2.0 为根目录许可证，但第三方 Pine 文件不被该许可证覆盖；本 ZIP 中的参考快照仅作该任务使用与验证。
- `original_delivery/MBV_V0.1_Deliverables.zip` 为用户本次交付的原始开发包，其中二进制缓存不作为可信源码，不应复制到最终项目。
