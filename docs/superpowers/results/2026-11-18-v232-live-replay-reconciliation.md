# v232 - Live versus replay reconciliation, per direction

> The live book is a paper book. Entries and exits are filled at a quote polled once a minute, with no spread, no queue, no partial fills, no rejected orders and no failed locates. Costs in this report are modelled (5 bps a fill, commission, 0.5% a year borrow on shorts), not paid, and borrow availability is not modelled at all. A stop that a real order would fill at a gapped open is filled here where the poll saw it. So this report measures the backtest against the paper engine. It does not show that either is achievable in a real account; the eToro demo stage is the first place that can be measured. The "unexplained" shares carry the same warning.

## How to read this

- Intervals: one-arm week-cluster bootstrap over entry weeks, descriptive; under-covers below 20 clusters. Tag means carry no interval; thin = under 30 trades or under 8 weeks.
- R is in the live trade's risk unit |live fill - issued stop|; costs are modelled.
- Exit effect = R_live - R_exit_only; entry effect = R_exit_only - R_as_backtest. The other order needs the backtest entry under live's intraday exits, which nobody observed, so the entry x exit interaction sits in the exit effect.
- The backtest's signal bar is the session of issue, so the entry effect includes the intraday drift from the live issue to the daily close.
- The era boundary (2026-09-15T08:54:50Z) and the manual-close rule were set after the book autopsy had read this book; acceptable for a description.
- Layer 2 replays the live scan with today's parameters, one decision a day at the close, without the strategy-sourced pass, alert cap, portfolio heat or live track record. Replay-only counts rest on replay holding periods (no replay outcome is stored or printed) and are a lower bound: removed tickers that never produced a plan or rejection are missing.
- Holdout: no outcome of a signal live did not trade is read; backtest R appears per direction, fill model and era only; the ledger split is shown for live figures only.
- Citation rule: a later spec may cite mechanism counts and shares from this report; it may not cite a backtest-R effect size from it as evidence, and it still owes its own screen or pre-registration.
- Cells shown: 200 (effect cells and tag means x directions x fill models x eras, plus layer 2 sub-reasons); read one large mean against that number.

## Run

- Commit 060035723822f39caa313b5b3f77506fcb38d904; window 2026-07-01 to 2026-11-18; scan parameters digest fcde4e8fd867f51b2be26c68dca2b97f3208f019ab064f2f2d0c1df6e5eb105a; live SHORT lanes none.
- Per-trade rows (git-ignored) SHA-256 9d9011a7d622a6745373106949f810f35a6591ac30561131ae8caa91f70c6315; inputs reconcile.jsonl ed4dff9b3417866f4cdca45fdda76507e3f28c08010eecbbfe82b1835bebe7f3; raw bars raw fc966a8bd7cb (85 ok, 2 empty, 1 unserved), split 2c0c62647e3b (85 ok, 2 empty, 1 unserved).
- Deploys inside the headline window (known confounds): 2026-10-01T12:43:36Z 14551c3cd6bc7b547a162c00c6b70a62b100144a, 2026-10-01T13:57:37Z 7adc8ec3aff2cd95515d716e25047a988c8f98df, 2026-10-01T17:20:54Z 6b9c09d0ac04f853a8b893d2c17ff4e018bae461, 2026-10-01T17:28:43Z fe292bdbd9d67830dd4ad7b20efb737b652864b6, 2026-10-01T18:51:02Z 275f6bb0ec1e6ed54f9a8acff1f6a55e75bd02f6, 2026-10-01T19:58:54Z 519452b054ebfc2fc5b6cfedd0a1c44545c941a7, 2026-10-01T20:28:22Z 34a06af46b2ec5fa77f4cd788a739182f339c379, 2026-10-01T21:32:43Z a0da07a7a09a489ef758b02d11639dd4d4e33de2, 2026-10-01T21:39:12Z 33580cbc3368f6b627b881d10a0e3787b283565d, 2026-10-01T21:55:40Z aabee1c11d8d760c0171e85a3381b0d682efee70, 2026-10-02T07:58:23Z 122b7444afe89fdff0a7d5338fcf61ca5c66e588, 2026-10-02T08:22:21Z 37962d6a2643b5ccdc0ef26e923d8e552429d242, 2026-10-02T08:41:22Z c74bbaefe4561e4d96772de897e4cd4c9a351aeb, 2026-10-02T08:45:03Z c74bbaefe4561e4d96772de897e4cd4c9a351aeb, 2026-10-02T14:40:23Z f109286d89eb7745ad5c22847d4f5c0d2c8139c7, 2026-10-02T15:27:12Z 669e332ee0262e3932233d072e2b08e3f581c7ea, 2026-10-04T12:14:35Z 38a9f356821bbfe6f57fcd2c2c8dfcf94d78c3f3, 2026-10-04T14:21:28Z c0cf9adb670020e1cdea63e743361d8a27b516b8, 2026-10-05T12:02:50Z 570e9568f5b2a384034c337db9a3b034a978e3ea, 2026-10-05T13:34:30Z fff6600453f69e6d0bdd94e1b71cdf2cf8382b04, 2026-10-05T15:46:37Z 2bc9a770419fbc9fc03e805fa4c72aa2076e4bb2, 2026-10-07T13:20:01Z e25cda9333ee561c6022fd2456baa78b22820bd0, 2026-10-07T14:06:01Z 802abebe5a7c635cb9a95d2d0e60a71713825931, 2026-10-08T12:09:42Z e0cf36be5674791734f2c72e52e0ede0a99e4fb8, 2026-10-09T09:46:36Z 655bb005190f6516718126834790c488d77a07b3, 2026-10-09T10:52:53Z 51a9a5f28b712b8f29b41e62f35a486c8c8a1fa8, 2026-10-09T11:17:00Z 16707dd234f2be9e3bbcf5f6a3d4e3106ea56628, 2026-10-09T11:26:36Z 137376e016d0c8f0af98e20c9d4653572ce17f55, 2026-10-09T11:46:09Z 613311ae382cd4dd06d0636ed80fce64bb1c8772, 2026-10-09T13:49:21Z c1ed126ba209b3d5bcfc2c993252226abe96ca37, 2026-10-09T14:02:33Z 36cbcc60bb3b756e64bc407237c23164040ee55b, 2026-10-09T14:32:17Z c183249e753bb2820131eaa6f32302ac26fccdfa, 2026-10-09T14:59:11Z 220d8dfac55e30554d0166f400ac6b70452ea8a8, 2026-10-10T07:02:20Z b66f0e1dc02a51528b6629dbe10679ab752c5c92, 2026-10-10T07:13:26Z 5969585613875f38a8fb4954bd9c1f8268a9da9b, 2026-10-10T12:20:15Z b180c8823d605fa6f4083a227c39af92839353f7, 2026-10-10T12:23:04Z b180c8823d605fa6f4083a227c39af92839353f7, 2026-10-10T13:11:24Z 76f60d481d849262051af791229a88be5a4a4f62, 2026-10-10T13:42:04Z 1ce5c475b80263fd70feb1b61d7ad01df19018b9, 2026-10-10T13:57:13Z b179e62ab3ffa77af6e2d95664c2f352ade373ec, 2026-10-10T14:39:11Z c23d79ad7e04cbe4e49d8e812959206744e43a1a, 2026-10-10T14:43:26Z 70d151c61f8f32467e963e42f18978d017a080dd, 2026-10-10T14:46:54Z 70d151c61f8f32467e963e42f18978d017a080dd, 2026-10-10T15:33:29Z 690501fad65866bf69f41e752d609d2aa37fd1c8, 2026-10-10T17:20:39Z c63776d664d566bcf522bd1c68d4bfc1ebed86ad, 2026-10-12T07:29:38Z fcabf6cd20b923c5b2ef242f23eafa6ae8a7f780, 2026-10-12T09:37:11Z 37fc95be1babb94fa12ca054a5649534489cff92, 2026-10-12T12:32:24Z 5c95fa42c77045996347aae38f64f9f88ef6e3fd, 2026-10-12T20:04:25Z 34d2b11bf84390ed37254eb60575217384f4d269, 2026-10-15T16:45:49Z 4aea5e7f965859ef2b2743f3c70d2ee31c5b8390, 2026-10-15T17:16:27Z 7052b1dfd62ee6c990df2af9ee1c36b4518fb57a, 2026-10-15T22:16:57Z b22e799e1c59cf94679b2d5f32c6573076854923, 2026-10-16T08:47:38Z 2a5d7df6d974be0041acd3cedaeeddc97ead03a3, 2026-10-16T09:12:11Z 1f5e94cedd2f28c20d1081b90ca36ff20f7dd36b, 2026-10-16T14:21:15Z 81843c8ede31c0b3e10f3b069c4ae474909ff3b7, 2026-10-16T14:26:15Z d5ebc93125ae20862192bc76e6e76c50f6796f5e, 2026-10-16T15:32:45Z 6a44da7e61c38ff0ce7c7f84a8d0c39ebd68f1a8, 2026-10-16T15:37:01Z 157cc0f099d33c643186c045bb62c98714e661a4, 2026-10-16T15:46:17Z e6675ffd789b56ded6c21db94fa7d88facc8abf1, 2026-10-16T19:42:18Z 14b2b877bb9191d0eb2696290a226cc620afb3b7, 2026-10-17T09:10:53Z 6058e20e08bc710a86feadc8c4b3975527db8bfa, 2026-10-17T09:39:36Z f0798e5a8ce4184add71314e1b8aec4f9e68042d, 2026-10-17T13:28:24Z 774dce637251098bc424201b4042075769c4ce08, 2026-10-17T14:03:52Z 0fd32edad31bf058959f250be1482e3ae8cfa26a, 2026-10-18T16:41:56Z 3ea7ef3cf7dd107c20b9febb487b8500ce87b4ec, 2026-10-18T18:51:47Z 47e4d36a660e2535340d5880d057019f9c1c2bb4, 2026-10-19T18:29:35Z f067dccc15dd007b10b1fdf575531d512d9e9696, 2026-10-19T20:28:30Z 656aa2da2666f2f9c6f94a0b85376d49e0892d1c, 2026-10-20T08:45:36Z 52073b7a021f36785684ffb172d7f538e54eb54b, 2026-10-20T10:03:09Z 06ac6f0f1669ee331c9b7a784ed9fce902cb80a6, 2026-10-20T15:32:41Z 618a486e6896d5868f2288ef097da4c2ffc2486c, 2026-10-20T15:41:44Z d80cc708b5ab619fc09dab226d77d14ae7817df8, 2026-10-20T18:36:44Z 5339c5eb8b6cfcc4cc8d04f9b20ab6cc8003b4d0, 2026-10-20T18:49:53Z 5707fe9c115a9bbaef111dfbbac58fb5cc9849f4, 2026-10-20T20:15:25Z a341865c335da940429971039b38c25de1e85925, 2026-10-21T07:47:31Z 0a180872573523470343d717280a7fa419382ea8, 2026-10-21T09:18:44Z ce7fc565e44d9aced0787982c34a0974a2827688, 2026-10-21T09:39:26Z f6da826533a9265b47448a393340f633827ac693, 2026-10-21T13:57:32Z 16964bc45fdb0581a826d1496913c6cff46cdaa0, 2026-10-21T14:44:07Z a041bee2cf006036582c383815771ea7269432e8, 2026-10-21T17:42:32Z 6715f9a9199a9dacd9142d6d7a915a48fc158d56, 2026-10-21T17:45:27Z 6715f9a9199a9dacd9142d6d7a915a48fc158d56, 2026-10-21T21:09:10Z 8bae3bab5ac143512846c2d00ac1c6114843d417, 2026-10-22T09:48:54Z 0d4fe73abee696c3c3c977eb1aa8821dd440b6de, 2026-10-22T12:59:27Z 107140ab2e52f0c1e0c685c1b641a7d899684043, 2026-10-23T09:43:18Z 9ba8a5a623fcb16910073bdfa36b909dd6df743d, 2026-10-23T12:59:34Z 0646fa34ec6a355fa1ab26a72631b7bdd69531af, 2026-10-23T15:09:52Z 751c5d0933d2ddc63ec845735348ca776ee7e888, 2026-10-23T16:37:41Z 6a5b7c55449e994e4b2807fe1b50a2294f6c1dbc, 2026-10-24T15:03:54Z b37c6e441058dbcf01f177daa710fea3d110d6a2, 2026-10-24T19:56:19Z c8fb1be8fcdfd0f5e85cdaed8b3c10e587b7423e, 2026-10-24T20:59:44Z 3add38361356c6036620907a2814341d3ced17d4, 2026-10-25T19:28:31Z 8e627d483018b5f481fd063303389620faf51e46, 2026-10-25T22:19:32Z f31834de4e30507245ad290cfade46239f2535cd, 2026-10-26T14:45:37Z 72d7784ee660f602ac89a0cb02d3f7b5b3c60458, 2026-10-28T15:12:22Z 0abd600a79a9f44f4759b2dcf9f9039c7e3f1f03, 2026-10-29T11:05:04Z 8d0f0f0e960a88777d210d94734f6c531624f844, 2026-10-29T13:38:12Z 1faac3fb6a0f4c39eee3423b5e54690f6e9d706e, 2026-10-29T14:26:32Z 004b2ca7dd401135bec8f029d66d3a357ae4e6f3, 2026-10-29T15:12:33Z 046ee439e9a7ed6e3824ed379e216400b08d8593, 2026-10-30T18:12:25Z a188f1f476076f3ddb2c9a501e9cf8d54a65c871, 2026-10-30T18:19:45Z 76be6af580d5ea16b8c2bf6513f982f957b7fb51, 2026-11-04T15:21:49Z 4b7160af40aaf7706d46a2d6a6de8da8ddd4b242, 2026-11-04T21:10:03Z 47fefba0675dadca08260ea58f3f24dbd96f0456, 2026-11-05T12:42:21Z 76e1fa5353dd8e504a2bc2a4735878214a61ab22, 2026-11-05T13:50:26Z 67d33bf256ee71d9db3126de7aa4232663711758, 2026-11-05T14:03:08Z 2fc791252ee1b8d256f063693e2e795a715cec8e, 2026-11-05T16:48:58Z d0500efab0ccfecaf14013703739b3def27f5631, 2026-11-06T10:21:10Z d071489ba500c6d79193d4d894f272ba3caccca3, 2026-11-06T10:25:22Z d5f56464e217f9d2b72695603a948104798ed096, 2026-11-06T12:21:16Z 68927fbd8cc2588347b049d4d4467bb5c2201751, 2026-11-06T15:32:07Z d71a55f99dbeb03337f3670dd6e62b16be86d44e, 2026-11-06T16:07:37Z 2365278852ecd5d6e82e0ae815b2bc1083ef69f0, 2026-11-06T16:43:16Z 7b17ccc000ae6a420589103fb3e3b907ec33a1f7, 2026-11-06T18:31:40Z f970e005eccff972d3e6fa554197debe0a2e5aad, 2026-11-06T19:08:58Z 8d4e87fe10d6e8e61f8e8ee163bfdff1bf868dc2, 2026-11-06T22:39:39Z c8a9f0ebea615ed8bef6998c11ea81fae3c66e3a, 2026-11-06T23:01:47Z 014f193f0816cd34f6709fa0f5375eb02859b775, 2026-11-06T23:06:27Z eb56492bd9ed4f96863a020c3099c6d3e410e741, 2026-11-06T23:30:19Z 06460bbe5985fc733d5c2466149fed9fd9c86c64, 2026-11-09T08:43:19Z 1027ba6b3059df36c0cde9d6b80b15495287cc13, 2026-11-09T14:25:46Z 214f490edae0824cc669709a4ed381f86491f6ac, 2026-11-09T14:53:48Z 86d3ec24ad8df752dde3cbecc4a11bf0debdb91c, 2026-11-10T09:15:37Z 50a970cb5dbbe878fcdea687dce2abc1665f8afb, 2026-11-10T11:31:46Z 82db01287cac3489b6ed53745b45bb442099c486, 2026-11-10T12:44:31Z 0fb1f9f0d365a086bedd49f52b39c9cc34270e29, 2026-11-10T12:53:29Z 997d7f5aea44e17646442cf97061403cc8b3e2a3, 2026-11-10T18:01:11Z e4802b0809d3705d001b1d3fdd19827032d9a959, 2026-11-10T20:56:40Z 8a43bfdd5a88e680c7844be7c7a925616e7f1c6c, 2026-11-10T21:18:25Z 00921d7b74e5650f2cc2bef0f9a3bad81f9d7c39, 2026-11-10T21:23:25Z 7ab2789a4c35f7be5a3c9bd1747b5d4fd7f0d03a, 2026-11-11T08:33:21Z 69f6bfeb8c9f8352ce5f67a1ba334b6b870154f9, 2026-11-11T08:54:48Z 24146ca0ad3f8fae76f4c7e51d6c9359b19d3dc7, 2026-11-11T11:20:03Z 1db35f947fcce94d9b87e83a4cf727ab4cd8061f, 2026-11-11T15:39:29Z e6595942ac7b5c8f3667f0b44042bf141b691176, 2026-11-11T16:02:59Z 5340ea5c6321ab056ad989aae2f80737a31c868e, 2026-11-11T16:14:03Z e135cb7d3b79a722896c16d0335c848394322f1e, 2026-11-12T14:15:43Z d388bf5c9abe256d3a3199f7a7c32b55d3b3aaf9, 2026-11-13T15:04:46Z b1d346871047e35a2a27e71593714e44a0c62522, 2026-11-13T15:15:37Z 42f16c50126701113d6050c91457a692c3cc89c8, 2026-11-13T21:51:28Z dcfc51950c2452d4b82ff02526820c75b3ba8d5e, 2026-11-13T21:57:21Z c84ea56e3e87ca5b67efe066ad8d6b832618d049, 2026-11-14T20:26:37Z 3432cbd5eca291d44939bf14cc6f38769ee00e0a, 2026-11-14T20:39:51Z bb017e01dfc0a57d320ba61ed74fd5c08e9148af, 2026-11-14T22:37:48Z 406e1538c7224db6d409161a68a9fda8285daef7, 2026-11-15T21:22:40Z ea4b7ce54674625284d449f12a597dd7da4508fd, 2026-11-16T09:56:36Z 63ceeee862f8330162f7394a1cb3e0c895ee95b6, 2026-11-16T10:59:47Z 59b0324108b0dd82f8a359b2a19f417023a23c9e, 2026-11-16T17:44:44Z f529526837c55af83304e1a50db3f8d3191001d7, 2026-11-16T18:29:46Z 1fcf7edf21eb2077bb6d2f550e49fcc9fc03ca40, 2026-11-17T15:46:51Z 206f5c5aa95386e17fcc4fa8a330243a5cb02cf9, 2026-11-17T15:55:49Z a2c7db93949c24aae7e0b3f98bcb3e1d07dd22fb, 2026-11-17T16:06:32Z d735b188f114fc1144e495306f3bf38ed065b91a, 2026-11-17T18:41:53Z a708c61eb5951e5415fe5c9a73f09b012e306275, 2026-11-17T18:49:15Z 5dd375ca454250f6aab5c1f86616dec43e0b40b8, 2026-11-17T18:59:12Z c19c55a00d98efe22408e3693c924101d9959a7c, 2026-11-17T19:15:29Z 5ab82afc4cfea8aee0f3fd0a7598c94c4e314e19, 2026-11-17T19:19:27Z 5ab82afc4cfea8aee0f3fd0a7598c94c4e314e19, 2026-11-17T19:55:35Z 734fe1820d474e105de9c0f114461c227ae14bb3, 2026-11-17T20:24:25Z 17a58dd5a07c078b2cea13812d05121f97e9c7b1.

## Populations

| Side | Era | closed | manual | still_open | unfilled | scored | would fill v1 (yes/no) | would fill v2 (yes/no) |
|---|---|---|---|---|---|---|---|---|
| long | headline | 420 | 15 | 7 | 52 | 413 | 42/10 | 42/10 |
| long | earlier | 269 | 8 | 0 | 9 | 268 | 8/1 | 2/7 |
| short | headline | 93 | 2 | 1 | 14 | 91 | 6/4 | 6/4 |
| short | earlier | 132 | 11 | 0 | 5 | 129 | 5/0 | 5/0 |

- long headline: live R from journal 434, from the trade doc 1; refused no_bars 6, split_in_window 1 (bars: no_bars XAGUSD, XAUUSD, split_in_window CRWD); unfilled reasons expired 1, invalidated 7, risk_cap 44.
- long earlier: live R from journal 227, from the trade doc 49; refused split_in_window 1, no_journal 1 (bars: split_in_window CRWD); unfilled reasons invalidated 2, unknown 7.
- short headline: live R from journal 95, from the trade doc 0; refused no_bars 6 (bars: no_bars GC=F, XAGUSD, XAUUSD); unfilled reasons invalidated 5, risk_cap 9.
- short earlier: live R from journal 132, from the trade doc 9; refused split_in_window 3, no_journal 2 (bars: split_in_window CRWD); unfilled reasons unknown 5.

## LONG, trades opened 2026-09-15 to 2026-11-18

### LONG, trades opened 2026-09-15 to 2026-11-18, v1 walk

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                   -153.30    412
  + entry effect (incl. intraday drift to the close)              +175.90    412
  + exit effect                                                    -20.70    412
  = Live, gross, scored trades                                      +1.90    412
  - modelled costs                                                 +31.11    412
  = Live, net, scored trades                                       -29.21    412
  + backtest would not have filled (live net)                       -1.07      1
  + manual closes (live net)                                        -0.41     15
  + not scoreable: bars refused (live net)                          -6.03      7
  = Live book, net                                                 -36.73    435

  Selection, counts only: matched 54 · live-only 440 · replay-only 18 · outside the replay (strategy-sourced) 0 · still open 7 · unfilled 52
```

Re-based backtest total (its own entry-to-stop unit) +1040.63R over 412 filled, 408 re-based; stop-distance shift % median +16.25, p90 +240.79 (n 412). Modelled cost effect -31.11R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 412 | 10 | +124.09 | +0.301 | [-0.063, +0.709] | 38% |  |
| entry effect (incl. intraday drift to the close) | 412 | 10 | +175.90 | +0.427 | [+0.155, +0.699] | 33% |  |
| exit effect (incl. the entry x exit interaction) | 412 | 10 | -20.70 | -0.050 | [-0.182, +0.114] | 22% |  |
| modelled costs (live net - live gross) | 412 | 10 | -31.11 | -0.075 | [-0.077, -0.074] | 21% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 83 | 18 | 3 | 1 |
| loss | 26 | 191 | 5 | 5 |
| scratch | 18 | 44 | 18 | 1 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 227 | -0.265 |
| wick_missed | 8 | +0.845 |
| both_levels_bar | 13 | +1.337 |
| gap_through | 41 | +0.572 |
| exit_outside_rth | 94 | -0.088 |
| entry_outside_rth | 94 | +0.036 |
| first_15min | 118 | +0.352 |
| live_stop_moved | 186 | +0.431 |
| levels_edited | 0 | n/a |
| scaled_out | 105 | +0.774 |
| time_stop | 0 | n/a |
| earnings_in_window | 28 | +0.452 |
| short_gap_against | 0 | n/a |
| outcome_flip_live_better | 18 | +2.818 |
| outcome_flip_live_worse | 26 | -3.212 |
| entry_slip | 6 | -0.254 |
| poll_fill | 82 | +0.497 |

### LONG, trades opened 2026-09-15 to 2026-11-18, v2 fills

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                   -146.14    296
  + entry effect (incl. intraday drift to the close)              +320.20    296
  + exit effect                                                    -74.24    296
  = Live, gross, scored trades                                     +99.82    296
  - modelled costs                                                 +22.30    296
  = Live, net, scored trades                                       +77.52    296
  + backtest would not have filled (live net)                     -107.81    117
  + manual closes (live net)                                        -0.41     15
  + not scoreable: bars refused (live net)                          -6.03      7
  = Live book, net                                                 -36.73    435

  Selection, counts only: matched 54 · live-only 440 · replay-only 18 · outside the replay (strategy-sourced) 0 · still open 7 · unfilled 52
```

Re-based backtest total (its own entry-to-stop unit) -75.86R over 296 filled, 293 re-based; stop-distance shift % median +52.15, p90 +323.29 (n 296). Modelled cost effect -22.30R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 296 | 10 | +223.66 | +0.756 | [+0.452, +1.017] | 29% |  |
| entry effect (incl. intraday drift to the close) | 296 | 10 | +320.20 | +1.082 | [+0.759, +1.373] | 30% |  |
| exit effect (incl. the entry x exit interaction) | 296 | 10 | -74.24 | -0.251 | [-0.579, +0.094] | 33% |  |
| modelled costs (live net - live gross) | 296 | 10 | -22.30 | -0.075 | [-0.077, -0.073] | 22% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 83 | 18 | 3 | 1 |
| loss | 26 | 191 | 5 | 5 |
| scratch | 18 | 44 | 18 | 1 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 227 | +0.151 |
| wick_missed | 8 | +0.793 |
| both_levels_bar | 13 | +1.337 |
| gap_through | 41 | +0.534 |
| exit_outside_rth | 94 | +0.685 |
| entry_outside_rth | 94 | +0.239 |
| first_15min | 118 | +0.523 |
| live_stop_moved | 186 | +0.459 |
| levels_edited | 0 | n/a |
| scaled_out | 105 | +0.444 |
| time_stop | 0 | n/a |
| earnings_in_window | 28 | +0.704 |
| short_gap_against | 0 | n/a |
| outcome_flip_live_better | 18 | +3.172 |
| outcome_flip_live_worse | 26 | -3.598 |
| entry_slip | 6 | -0.294 |
| poll_fill | 82 | +0.379 |

## LONG, trades opened before 2026-09-15 (includes code changes)

### LONG, trades opened before 2026-09-15 (includes code changes), v1 walk

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                    -17.19    260
  + entry effect (incl. intraday drift to the close)               +28.86    260
  + exit effect                                                    -54.35    260
  = Live, gross, scored trades                                     -42.68    260
  - modelled costs                                                 +16.35    260
  = Live, net, scored trades                                       -59.03    260
  + backtest would not have filled (live net)                       -4.07      8
  + manual closes (live net)                                       +17.79      7
  + not scoreable: bars refused (live net); 1 without live R (no R in journal or trade doc, or zero risk), counted at 0R    -1.08      2
  = Live book, net                                                 -46.39    277

  Selection, counts only: matched 26 · live-only 260 · replay-only 80 · outside the replay (strategy-sourced) 0 · still open 0 · unfilled 9
```

Re-based backtest total (its own entry-to-stop unit) +119.52R over 260 filled, 244 re-based; stop-distance shift % median +0.00, p90 +163.37 (n 260). Modelled cost effect -16.35R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 260 | 8 | -41.84 | -0.161 | [-0.355, +0.021] | 54% |  |
| entry effect (incl. intraday drift to the close) | 260 | 8 | +28.86 | +0.111 | [+0.008, +0.239] | 44% |  |
| exit effect (incl. the entry x exit interaction) | 260 | 8 | -54.35 | -0.209 | [-0.483, +0.025] | 57% |  |
| modelled costs (live net - live gross) | 260 | 8 | -16.35 | -0.063 | [-0.064, -0.061] | 29% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 90 | 40 | 0 | 0 |
| loss | 23 | 82 | 6 | 0 |
| scratch | 7 | 13 | 7 | 0 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 179 | -0.044 |
| wick_missed | 1 | +0.000 |
| both_levels_bar | 4 | +1.052 |
| gap_through | 18 | -1.909 |
| exit_outside_rth | 82 | -0.215 |
| entry_outside_rth | 69 | +0.229 |
| first_15min | 38 | +0.202 |
| live_stop_moved | 159 | +0.167 |
| levels_edited | 0 | n/a |
| scaled_out | 107 | +0.211 |
| time_stop | 0 | n/a |
| earnings_in_window | 0 | n/a |
| short_gap_against | 0 | n/a |
| outcome_flip_live_better | 40 | +1.484 |
| outcome_flip_live_worse | 23 | -2.987 |
| entry_slip | 10 | -0.174 |
| poll_fill | 64 | -0.751 |

### LONG, trades opened before 2026-09-15 (includes code changes), v2 fills

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                    -53.94    221
  + entry effect (incl. intraday drift to the close)              +265.57    221
  + exit effect                                                   -236.08    221
  = Live, gross, scored trades                                     -24.45    221
  - modelled costs                                                 +13.87    221
  = Live, net, scored trades                                       -38.32    221
  + backtest would not have filled (live net)                      -24.78     47
  + manual closes (live net)                                       +17.79      7
  + not scoreable: bars refused (live net); 1 without live R (no R in journal or trade doc, or zero risk), counted at 0R    -1.08      2
  = Live book, net                                                 -46.39    277

  Selection, counts only: matched 26 · live-only 260 · replay-only 80 · outside the replay (strategy-sourced) 0 · still open 0 · unfilled 9
```

Re-based backtest total (its own entry-to-stop unit) -7.43R over 221 filled, 207 re-based; stop-distance shift % median +49.06, p90 +313.75 (n 221). Modelled cost effect -13.87R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 221 | 8 | +15.62 | +0.071 | [-0.182, +0.287] | 26% |  |
| entry effect (incl. intraday drift to the close) | 221 | 8 | +265.57 | +1.202 | [+0.354, +1.718] | 48% |  |
| exit effect (incl. the entry x exit interaction) | 221 | 8 | -236.08 | -1.068 | [-1.562, -0.194] | 47% |  |
| modelled costs (live net - live gross) | 221 | 8 | -13.87 | -0.063 | [-0.064, -0.061] | 29% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 90 | 40 | 0 | 0 |
| loss | 23 | 82 | 6 | 0 |
| scratch | 7 | 13 | 7 | 0 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 179 | -0.633 |
| wick_missed | 1 | +0.055 |
| both_levels_bar | 4 | +1.052 |
| gap_through | 18 | -4.016 |
| exit_outside_rth | 82 | -0.444 |
| entry_outside_rth | 69 | +0.096 |
| first_15min | 38 | +0.151 |
| live_stop_moved | 159 | -0.334 |
| levels_edited | 0 | n/a |
| scaled_out | 107 | -0.390 |
| time_stop | 0 | n/a |
| earnings_in_window | 0 | n/a |
| short_gap_against | 0 | n/a |
| outcome_flip_live_better | 40 | +1.711 |
| outcome_flip_live_worse | 23 | -4.573 |
| entry_slip | 10 | +0.015 |
| poll_fill | 64 | -1.442 |

## SHORT, trades opened 2026-09-15 to 2026-11-18

### SHORT, trades opened 2026-09-15 to 2026-11-18, v1 walk

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                    +27.60     88
  + entry effect (incl. intraday drift to the close)               +15.39     88
  + exit effect                                                    -28.58     88
  = Live, gross, scored trades                                     +14.41     88
  - modelled costs                                                  +6.54     88
  = Live, net, scored trades                                        +7.87     88
  + backtest would not have filled (live net)                       -2.22      3
  + manual closes (live net)                                        +2.35      2
  + not scoreable: bars refused (live net)                          -0.14      2
  = Live book, net                                                  +7.86     95

  Selection, counts only: matched 10 · live-only 100 · replay-only 5 · outside the replay (strategy-sourced) 0 · still open 1 · unfilled 14
```

Re-based backtest total (its own entry-to-stop unit) +163.45R over 88 filled, 88 re-based; stop-distance shift % median +34.10, p90 +225.19 (n 88). Modelled cost effect -6.54R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 88 | 9 | -19.72 | -0.224 | [-1.117, +0.876] | 29% |  |
| entry effect (incl. intraday drift to the close) | 88 | 9 | +15.39 | +0.175 | [-0.424, +0.644] | 32% |  |
| exit effect (incl. the entry x exit interaction) | 88 | 9 | -28.58 | -0.325 | [-0.897, +0.404] | 46% |  |
| modelled costs (live net - live gross) | 88 | 9 | -6.54 | -0.074 | [-0.075, -0.071] | 32% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 22 | 4 | 1 | 0 |
| loss | 10 | 35 | 2 | 0 |
| scratch | 3 | 9 | 4 | 1 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 58 | -0.327 |
| wick_missed | 1 | +2.502 |
| both_levels_bar | 3 | +1.333 |
| gap_through | 8 | +0.678 |
| exit_outside_rth | 23 | -0.453 |
| entry_outside_rth | 26 | -0.081 |
| first_15min | 22 | +0.080 |
| live_stop_moved | 44 | +0.276 |
| levels_edited | 0 | n/a |
| scaled_out | 27 | +0.479 |
| time_stop | 0 | n/a |
| earnings_in_window | 8 | -0.909 |
| short_gap_against | 1 | +0.983 |
| outcome_flip_live_better | 4 | +3.120 |
| outcome_flip_live_worse | 10 | -3.209 |
| entry_slip | 10 | +0.567 |
| poll_fill | 24 | -0.165 |

### SHORT, trades opened 2026-09-15 to 2026-11-18, v2 fills

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                    +51.41     75
  + entry effect (incl. intraday drift to the close)               +30.06     75
  + exit effect                                                    -49.87     75
  = Live, gross, scored trades                                     +31.61     75
  - modelled costs                                                  +5.60     75
  = Live, net, scored trades                                       +26.01     75
  + backtest would not have filled (live net)                      -20.35     16
  + manual closes (live net)                                        +2.35      2
  + not scoreable: bars refused (live net)                          -0.14      2
  = Live book, net                                                  +7.86     95

  Selection, counts only: matched 10 · live-only 100 · replay-only 5 · outside the replay (strategy-sourced) 0 · still open 1 · unfilled 14
```

Re-based backtest total (its own entry-to-stop unit) +19.20R over 75 filled, 75 re-based; stop-distance shift % median +46.78, p90 +309.08 (n 75). Modelled cost effect -5.60R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 75 | 9 | -25.41 | -0.339 | [-1.143, +0.680] | 31% |  |
| entry effect (incl. intraday drift to the close) | 75 | 9 | +30.06 | +0.401 | [-0.050, +0.875] | 27% |  |
| exit effect (incl. the entry x exit interaction) | 75 | 9 | -49.87 | -0.665 | [-1.355, +0.111] | 60% |  |
| modelled costs (live net - live gross) | 75 | 9 | -5.60 | -0.075 | [-0.075, -0.073] | 31% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 22 | 4 | 1 | 0 |
| loss | 10 | 35 | 2 | 0 |
| scratch | 3 | 9 | 4 | 1 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 58 | -0.065 |
| wick_missed | 1 | +0.606 |
| both_levels_bar | 3 | +1.345 |
| gap_through | 8 | +0.140 |
| exit_outside_rth | 23 | -0.258 |
| entry_outside_rth | 26 | -0.004 |
| first_15min | 22 | +0.253 |
| live_stop_moved | 44 | -0.187 |
| levels_edited | 0 | n/a |
| scaled_out | 27 | -0.346 |
| time_stop | 0 | n/a |
| earnings_in_window | 8 | -1.052 |
| short_gap_against | 1 | +0.983 |
| outcome_flip_live_better | 4 | +3.471 |
| outcome_flip_live_worse | 10 | -3.502 |
| entry_slip | 10 | +1.053 |
| poll_fill | 24 | -0.859 |

## SHORT, trades opened before 2026-09-15 (includes code changes)

### SHORT, trades opened before 2026-09-15 (includes code changes), v1 walk

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                    -61.68    127
  + entry effect (incl. intraday drift to the close)                +1.53    127
  + exit effect                                                    +26.08    127
  = Live, gross, scored trades                                     -34.06    127
  - modelled costs                                                  +7.95    127
  = Live, net, scored trades                                       -42.01    127
  + backtest would not have filled (live net)                       +0.46      2
  + manual closes (live net)                                        +9.30      9
  + not scoreable: bars refused (live net); 2 without live R (no R in journal or trade doc, or zero risk), counted at 0R    +1.64      5
  = Live book, net                                                 -30.60    143

  Selection, counts only: matched 2 · live-only 146 · replay-only 21 · outside the replay (strategy-sourced) 0 · still open 0 · unfilled 5
```

Re-based backtest total (its own entry-to-stop unit) +2.13R over 127 filled, 118 re-based; stop-distance shift % median -3.68, p90 +111.34 (n 127). Modelled cost effect -7.95R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 127 | 8 | +19.67 | +0.155 | [-0.269, +0.475] | 28% |  |
| entry effect (incl. intraday drift to the close) | 127 | 8 | +1.53 | +0.012 | [-0.177, +0.220] | 31% |  |
| exit effect (incl. the entry x exit interaction) | 127 | 8 | +26.08 | +0.205 | [-0.073, +0.390] | 30% |  |
| modelled costs (live net - live gross) | 127 | 8 | -7.95 | -0.063 | [-0.067, -0.061] | 49% |  |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 24 | 40 | 0 | 0 |
| loss | 11 | 49 | 2 | 0 |
| scratch | 1 | 1 | 1 | 0 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 101 | +0.198 |
| wick_missed | 0 | n/a |
| both_levels_bar | 4 | +0.155 |
| gap_through | 7 | +1.488 |
| exit_outside_rth | 44 | -0.096 |
| entry_outside_rth | 34 | +0.057 |
| first_15min | 10 | +0.030 |
| live_stop_moved | 72 | +0.611 |
| levels_edited | 0 | n/a |
| scaled_out | 57 | +0.639 |
| time_stop | 0 | n/a |
| earnings_in_window | 0 | n/a |
| short_gap_against | 8 | +1.436 |
| outcome_flip_live_better | 40 | +1.466 |
| outcome_flip_live_worse | 11 | -1.837 |
| entry_slip | 7 | +0.836 |
| poll_fill | 26 | -0.058 |

### SHORT, trades opened before 2026-09-15 (includes code changes), v2 fills

```
                                                                total R      N
  Backtest of the plans live traded (zero cost)                    -73.42     90
  + entry effect (incl. intraday drift to the close)               +20.35     90
  + exit effect                                                    +36.33     90
  = Live, gross, scored trades                                     -16.73     90
  - modelled costs                                                  +5.64     90
  = Live, net, scored trades                                       -22.37     90
  + backtest would not have filled (live net)                      -19.18     39
  + manual closes (live net)                                        +9.30      9
  + not scoreable: bars refused (live net); 2 without live R (no R in journal or trade doc, or zero risk), counted at 0R    +1.64      5
  = Live book, net                                                 -30.60    143

  Selection, counts only: matched 2 · live-only 146 · replay-only 21 · outside the replay (strategy-sourced) 0 · still open 0 · unfilled 5
```

Re-based backtest total (its own entry-to-stop unit) -18.08R over 90 filled, 81 re-based; stop-distance shift % median +4.91, p90 +175.62 (n 90). Modelled cost effect -5.64R against a zero-cost backtest, +0.00R against an equally costed one (zero by construction; a check).

| Effect | N | weeks | total R | mean | interval (descriptive; under-covers below 20 clusters) | largest week | thin |
|---|---|---|---|---|---|---|---|
| live net - backtest | 90 | 7 | +51.05 | +0.567 | [-0.034, +0.794] | 65% | thin |
| entry effect (incl. intraday drift to the close) | 90 | 7 | +20.35 | +0.226 | [+0.072, +0.309] | 50% | thin |
| exit effect (incl. the entry x exit interaction) | 90 | 7 | +36.33 | +0.404 | [-0.122, +0.635] | 67% | thin |
| modelled costs (live net - live gross) | 90 | 7 | -5.64 | -0.063 | [-0.066, -0.061] | 51% | thin |

| live \ exit-only | win | loss | scratch | timeout |
|---|---|---|---|---|
| win | 24 | 40 | 0 | 0 |
| loss | 11 | 49 | 2 | 0 |
| scratch | 1 | 1 | 1 | 0 |
| timeout | 0 | 0 | 0 | 0 |

| Tag | N | mean exit effect (no interval) |
|---|---|---|
| same_day_exit | 101 | +0.930 |
| wick_missed | 0 | n/a |
| both_levels_bar | 4 | +0.155 |
| gap_through | 7 | +2.104 |
| exit_outside_rth | 44 | +0.586 |
| entry_outside_rth | 34 | +0.649 |
| first_15min | 10 | +0.054 |
| live_stop_moved | 72 | +1.320 |
| levels_edited | 0 | n/a |
| scaled_out | 57 | +1.532 |
| time_stop | 0 | n/a |
| earnings_in_window | 0 | n/a |
| short_gap_against | 8 | +2.069 |
| outcome_flip_live_better | 40 | +2.618 |
| outcome_flip_live_worse | 11 | -1.759 |
| entry_slip | 7 | +2.764 |
| poll_fill | 26 | +0.984 |

## Entry slip, poll fill and gaps (live against its own levels)

| Side | Era | measure | N | median | p90 |
|---|---|---|---|---|---|
| long | headline | entry_slip_bps | 413 | +0.00 | +0.00 |
| long | headline | entry_slip_r | 413 | +0.00 | +0.00 |
| long | headline | poll_fill_bps | 332 | +0.00 | +30.32 |
| long | headline | poll_fill_r | 332 | +0.00 | +0.18 |
| long | headline | gap_r | 41 | +0.25 | +2.49 |
| long | headline | gap_pct | 41 | +0.42 | +4.34 |
| long | headline | exit_vs_open_r | 41 | +0.43 | +1.87 |
| long | headline | exit_vs_stop_r | 41 | +2.30 | +6.13 |
| long | earlier | entry_slip_bps | 268 | +0.00 | +0.00 |
| long | earlier | entry_slip_r | 268 | +0.00 | +0.00 |
| long | earlier | poll_fill_bps | 107 | +5.33 | +344.29 |
| long | earlier | poll_fill_r | 107 | +0.02 | +1.17 |
| long | earlier | gap_r | 18 | +1.68 | +3.06 |
| long | earlier | gap_pct | 18 | +4.50 | +6.71 |
| long | earlier | exit_vs_open_r | 18 | -3.92 | -0.18 |
| long | earlier | exit_vs_stop_r | 18 | -0.18 | +3.45 |
| short | headline | entry_slip_bps | 91 | +0.00 | +9.27 |
| short | headline | entry_slip_r | 91 | +0.00 | +0.05 |
| short | headline | poll_fill_bps | 74 | +0.00 | +34.34 |
| short | headline | poll_fill_r | 74 | +0.00 | +0.20 |
| short | headline | gap_r | 8 | +2.81 | +3.77 |
| short | headline | gap_pct | 8 | -5.27 | -1.43 |
| short | headline | exit_vs_open_r | 8 | +0.81 | +1.91 |
| short | headline | exit_vs_stop_r | 8 | +4.41 | +6.61 |
| short | earlier | entry_slip_bps | 129 | +0.00 | +0.00 |
| short | earlier | entry_slip_r | 129 | +0.00 | +0.00 |
| short | earlier | poll_fill_bps | 43 | +15.99 | +137.40 |
| short | earlier | poll_fill_r | 43 | +0.07 | +0.67 |
| short | earlier | gap_r | 7 | -1.46 | -0.85 |
| short | earlier | gap_pct | 7 | +4.50 | +4.66 |
| short | earlier | exit_vs_open_r | 7 | +1.77 | +2.13 |
| short | earlier | exit_vs_stop_r | 7 | +0.96 | +1.84 |

## Live net R by ledger (live figures only)

| Side | Era | Ledger | N | weeks | total R | mean |
|---|---|---|---|---|---|---|
| long | headline | main | 435 | 10 | -36.73 | -0.084 |
| long | earlier | main | 276 | 8 | -46.39 | -0.168 |
| short | headline | main | 95 | 10 | +7.86 | +0.083 |
| short | earlier | main | 141 | 8 | -30.60 | -0.217 |

## Layer 2: which signals each side took (counts only, no R)

- Coverage: 98 decision sessions; SPY missing False; panel gaps none; snapshot missing none; extra-lane bars missing none; base tickers with missing sessions GC=F 98, XAGUSD 98, XAUUSD 98.
- long headline: matched 54 (entry % median -0.02, p90 +0.81 (n 54); stop ratio median +1.00, p90 +1.06 (n 54); target ratio median +0.99, p90 +1.09 (n 54)); live-only 440 (open_to_1030 100, mid_day 205, last_hour 22, outside_session 112, created_at 1; unexplained share 25%; live net -33.68R over 386); replay-only 18 (gate_rejection 0, open_position 0, unexplained 18; gates none); outside the replay (strategy-sourced) 0.
- long earlier: matched 26 (entry % median -0.13, p90 +5.63 (n 26); stop ratio median +0.83, p90 +0.91 (n 26); target ratio median +1.28, p90 +4.62 (n 26)); live-only 260 (open_to_1030 49, mid_day 104, last_hour 15, outside_session 56, created_at 36; unexplained share 22%; live net -48.40R over 252); replay-only 80 (gate_rejection 0, open_position 5, unexplained 75; gates none); outside the replay (strategy-sourced) 0.
- short headline: matched 10 (entry % median -0.38, p90 +1.00 (n 10); stop ratio median +1.00, p90 +1.04 (n 10); target ratio median +0.99, p90 +1.03 (n 10)); live-only 100 (open_to_1030 28, mid_day 37, last_hour 3, outside_session 32, created_at 0; unexplained share 32%; live net +7.99R over 85); replay-only 5 (gate_rejection 1, open_position 0, unexplained 4; gates rs 1); outside the replay (strategy-sourced) 0.
- short earlier: matched 2 (entry % median +0.03, p90 +2.71 (n 2); stop ratio median +0.60, p90 +0.65 (n 2); target ratio median +4.26, p90 +4.66 (n 2)); live-only 146 (open_to_1030 21, mid_day 68, last_hour 8, outside_session 25, created_at 24; unexplained share 17%; live net -31.19R over 139); replay-only 21 (gate_rejection 0, open_position 2, unexplained 19; gates none); outside the replay (strategy-sourced) 0.

