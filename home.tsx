"use client";

import { useEffect } from "react";

const styles = String.raw`@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{
  --bg:#FFFFFF;
  --ink:#171717;
  --ink-2:#4D4D4D;
  --ink-3:#787878;
  --ink-4:#A3A3A3;
  --line:#EBEBEB;
  --line-2:#F2F2F2;
  --raise:#FAFAFA;
  --blue:#2154D6;
  --blue-ink:#1B47BE;
  --blue-wash:#F2F5FD;
  --dark:#0E0F11;
  --dark-2:#17181B;
  --dark-line:#26272B;
  --dark-ink:#EDEDED;
  --dark-ink-2:#9B9DA4;
  --dark-ink-3:#666870;
  --red:#B0463C;
  --hair:0 0 0 1px var(--line);
  --ease:cubic-bezier(0.16,1,0.3,1);
  --maxw:1360px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  background:var(--bg);color:var(--ink);
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-feature-settings:'cv05','ss01';
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  line-height:1.5;letter-spacing:-.006em;
  overflow-x:hidden;
}
a{color:inherit;text-decoration:none}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace}
.tnum{font-variant-numeric:tabular-nums}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 40px}
.eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--blue)}

/* buttons */
.btn{font-family:inherit;font-size:14px;font-weight:500;border-radius:8px;padding:10px 17px;cursor:pointer;
  border:1px solid transparent;white-space:nowrap;transition:background .18s var(--ease),border-color .18s var(--ease),color .18s var(--ease);
  display:inline-flex;align-items:center;gap:8px;letter-spacing:0}
.btn-primary{background:var(--ink);color:#fff}
.btn-primary:hover{background:#000}
.btn-secondary{background:var(--bg);box-shadow:var(--hair);color:var(--ink)}
.btn-secondary:hover{background:var(--raise)}
.btn-ghost{color:var(--ink-2)}
.btn-ghost:hover{color:var(--ink)}
.arr{transition:transform .18s var(--ease)}
.btn-primary:hover .arr,.link:hover .arr{transform:translateX(2px)}

/* ---------- NAV ---------- */
header{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.92);backdrop-filter:saturate(180%) blur(16px);
  box-shadow:0 1px 0 var(--line);transition:background .25s var(--ease),box-shadow .25s var(--ease)}
header.scrolled{background:rgba(255,255,255,.97);box-shadow:0 1px 0 #e3e3e3,0 8px 30px rgba(23,23,23,.035)}
.nav{display:flex;align-items:center;justify-content:flex-start;height:82px}
.brand{font-weight:650;font-size:20px;letter-spacing:-.04em;margin-right:46px}
.nav-mid{display:flex;align-items:center;gap:6px}
.nav-mid a{font-size:14px;color:#414141;padding:9px 12px;border-radius:7px;font-weight:500;transition:color .15s,background .15s}
.nav-mid a:hover{color:var(--ink);background:var(--line-2)}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:8px;padding-left:30px;position:relative}
.nav-right:before{content:"";position:absolute;left:10px;top:50%;width:1px;height:28px;background:var(--line);transform:translateY(-50%)}
.nav-right .btn-ghost{padding:11px 14px}
.nav-right .btn-primary{padding:12px 18px;border-radius:9px}
.nav-toggle{display:none;background:none;border:none;cursor:pointer;padding:6px}
.m-menu{display:none}

/* ---------- HERO ---------- */
.hero{padding:96px 0 0}
.hero h1{font-size:clamp(56px,6.8vw,88px);line-height:.96;letter-spacing:-.06em;font-weight:600;max-width:1100px;white-space:nowrap}
.hero-sub{margin-top:30px;font-size:18px;line-height:1.58;color:#68707d;max-width:720px;font-weight:400;letter-spacing:-.018em}
.hero-cta{display:flex;gap:11px;margin-top:32px;align-items:center;flex-wrap:wrap}
.hero-cta .btn{padding:11px 20px;font-size:15px}
.hero-trust{margin-top:24px;font-size:13.5px;color:var(--ink-3);display:flex;align-items:center;gap:9px;letter-spacing:0}
.hero-trust .dot{width:3px;height:3px;border-radius:50%;background:var(--ink-4)}

/* ---------- PRODUCT: DECISION FEED ---------- */
.product{padding:44px 0 20px}
.feed{background:var(--bg);border-radius:16px;overflow:hidden;box-shadow:var(--hair),0 1px 2px rgba(23,23,23,.03),0 32px 64px -36px rgba(23,23,23,.18)}
.feed-bar{display:flex;align-items:center;justify-content:space-between;padding:18px 26px;box-shadow:0 1px 0 var(--line)}
.feed-bar-l{display:flex;align-items:baseline;gap:12px}
.feed-title{font-size:15px;font-weight:600;letter-spacing:-.015em}
.feed-meta{font-size:13px;color:var(--ink-3)}
.disp-legend{display:flex;gap:7px}
.dl{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:600;letter-spacing:.04em;padding:5px 10px;border-radius:6px;line-height:1}
.dl .sq{width:7px;height:7px;border-radius:2px}
.dl.act{color:#256B45;background:#EDF5F0}  .dl.act .sq{background:#2E8257}
.dl.test{color:var(--blue-ink);background:var(--blue-wash)} .dl.test .sq{background:var(--blue)}
.dl.avoid{color:#94514A;background:#F7EFEE} .dl.avoid .sq{background:#B0655C}
.dl.bau{color:var(--ink-2);background:var(--line-2)} .dl.bau .sq{background:var(--ink-4)}

.drow{display:grid;grid-template-columns:92px 1fr 236px 160px;gap:26px;align-items:center;padding:28px 26px;
  box-shadow:0 1px 0 var(--line-2);position:relative;transition:background .15s var(--ease)}
.drow:last-of-type{box-shadow:none}
.drow:hover{background:var(--raise)}
.drow-accent{position:absolute;left:0;top:0;bottom:0;width:3px;background:transparent}
.drow.rec .drow-accent{background:var(--blue)}
.dstat{display:flex;flex-direction:column;gap:9px}
.dstat .stag{font-size:11px;font-weight:600;letter-spacing:.06em;line-height:1;display:inline-flex;align-items:center;gap:8px;width:fit-content}
.dstat .stag .sq{width:8px;height:8px;border-radius:2px}
.dstat .stag.test{color:var(--blue-ink)} .dstat .stag.test .sq{background:var(--blue)}
.dstat .stag.bau{color:var(--ink-2)} .dstat .stag.bau .sq{background:var(--ink-4)}
.dstat .stag.avoid{color:#94514A} .dstat .stag.avoid .sq{background:#B0655C}
.dstat .dcat{font-size:11px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-4)}
.dmain{min-width:0}
.dtitle{font-size:17px;font-weight:550;letter-spacing:-.018em;line-height:1.28}
.dsub{font-size:14px;color:var(--ink-2);margin-top:8px;line-height:1.5;max-width:52ch}
.dsub b{color:var(--ink);font-weight:500}
.decon{text-align:right}
.decon .val{font-size:26px;font-weight:600;letter-spacing:-.025em;line-height:1;font-variant-numeric:tabular-nums}
.decon .val.flat{color:var(--ink-3)} .decon .val.neg{color:#94514A}
.decon .lbl{font-size:12.5px;color:var(--ink-3);margin-top:9px}
.dconf{display:flex;flex-direction:column;gap:9px}
.dconf .ctop{display:flex;align-items:baseline;justify-content:space-between}
.dconf .cnum{font-size:16px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.dconf .clbl{font-size:11.5px;color:var(--ink-3)}
.dconf.rec .cnum{color:var(--blue-ink)}
.cbar{height:4px;border-radius:2px;background:var(--line-2);overflow:hidden}
.cfill{height:100%;border-radius:2px;background:var(--ink-4)}
.dconf.rec .cfill{background:var(--blue)}
.evi{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-3)}
.evi .ebars{display:flex;gap:2.5px}
.evi .ebars i{width:4px;height:12px;border-radius:1px;background:var(--line)}
.evi .ebars i.on{background:var(--ink-3)}
.dconf.rec .evi .ebars i.on{background:var(--blue)}
.feed-foot{padding:16px 26px;box-shadow:0 -1px 0 var(--line);display:flex;align-items:center;justify-content:space-between;background:var(--raise)}
.feed-foot .fnote{font-size:12px;color:var(--ink-4)}
.feed-foot .flink{font-size:12.5px;color:var(--ink-2);font-weight:500;display:inline-flex;align-items:center;gap:6px}

/* ---------- SECTION 1: EDITORIAL + BENTO ---------- */
.editorial{padding:132px 0 0}
.ed-head{max-width:900px}
.ed-head .eyebrow{display:block;margin-bottom:20px}
.editorial h2{font-size:clamp(32px,4.4vw,56px);line-height:1.04;letter-spacing:-.036em;font-weight:600;max-width:18ch}
.editorial h2 .muted{color:var(--ink-4)}
.bento{margin-top:56px;display:grid;grid-template-columns:1.35fr 1fr;grid-auto-rows:minmax(0,auto);gap:16px}
.tile{border-radius:14px;box-shadow:var(--hair);background:var(--bg);overflow:hidden;display:flex;flex-direction:column;min-height:280px}
.tile-wide{grid-row:span 2}
.tile-cap{padding:20px 22px 22px;border-top:1px solid var(--line-2);margin-top:auto}
.tile-cap .k{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-4);margin-bottom:9px}
.tile-cap .t{font-size:15px;font-weight:550;letter-spacing:-.015em}
.tile-cap .d{font-size:13px;color:var(--ink-2);margin-top:6px;line-height:1.5;max-width:40ch}
.tile-viz{flex:1;padding:24px;display:flex;align-items:center;justify-content:center;background:var(--raise)}

/* tile A — expanded decision row crop */
.crop-row{width:100%;background:var(--bg);border-radius:10px;box-shadow:var(--hair);overflow:hidden}
.crop-row .cr-top{padding:16px 18px;display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.crop-row .cr-stat{font-size:11px;font-weight:600;letter-spacing:.06em;color:var(--blue-ink);display:inline-flex;align-items:center;gap:7px;margin-bottom:10px}
.crop-row .cr-stat .sq{width:8px;height:8px;border-radius:2px;background:var(--blue)}
.crop-row .cr-title{font-size:15px;font-weight:550;letter-spacing:-.015em;line-height:1.3}
.crop-row .cr-val{font-size:22px;font-weight:600;letter-spacing:-.025em;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.crop-row .cr-vlbl{font-size:11px;color:var(--ink-3);text-align:right;margin-top:5px}
.crop-row .cr-econ{padding:0 18px 16px}
.cr-line{display:grid;grid-template-columns:88px 1fr 56px;gap:10px;align-items:center;padding:7px 0;box-shadow:0 1px 0 var(--line-2)}
.cr-line:last-child{box-shadow:none}
.cr-line .ck{font-size:12px;color:var(--ink-2)}
.cr-line .ctrack{height:5px;border-radius:3px;background:var(--line-2);position:relative;overflow:hidden}
.cr-line .cf{position:absolute;top:0;bottom:0;border-radius:3px}
.cr-line .cf.up{background:var(--ink);left:50%} .cr-line .cf.down{background:var(--ink-4);right:50%} .cr-line .cf.blue{background:var(--blue);left:50%}
.cr-line .cx{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--line)}
.cr-line .cv{font-size:12px;text-align:right;font-variant-numeric:tabular-nums;font-weight:500}
.cr-line .cv.blue{color:var(--blue-ink)}

/* tile B — evidence popover */
.crop-evi{width:100%;background:var(--bg);border-radius:10px;box-shadow:var(--hair);padding:18px}
.crop-evi .ce-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.crop-evi .ce-t{font-size:13px;font-weight:600;letter-spacing:-.01em}
.crop-evi .ce-pct{font-size:13px;font-weight:600;color:var(--blue-ink);font-variant-numeric:tabular-nums}
.crop-evi .ce-row{display:flex;align-items:center;justify-content:space-between;padding:9px 0;box-shadow:0 1px 0 var(--line-2);font-size:12.5px}
.crop-evi .ce-row:last-child{box-shadow:none}
.crop-evi .ce-row .k{color:var(--ink-2)}
.crop-evi .ce-row .v{font-weight:500;font-variant-numeric:tabular-nums}
.ce-ebars{display:flex;gap:3px}
.ce-ebars i{width:4px;height:12px;border-radius:1px;background:var(--line)}
.ce-ebars i.on{background:var(--blue)}

/* tile C — status filter */
.crop-filter{width:100%;display:flex;flex-direction:column;gap:9px}
.cfil-row{display:flex;align-items:center;gap:11px;background:var(--bg);border-radius:9px;box-shadow:var(--hair);padding:11px 14px}
.cfil-row .sq{width:8px;height:8px;border-radius:2px;flex:none}
.cfil-row .nm{font-size:12.5px;font-weight:550;letter-spacing:.02em}
.cfil-row .ct{margin-left:auto;font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums}
.cfil-row.act .sq{background:#2E8257} .cfil-row.act .nm{color:#256B45}
.cfil-row.test .sq{background:var(--blue)} .cfil-row.test .nm{color:var(--blue-ink)}
.cfil-row.avoid .sq{background:#B0655C} .cfil-row.avoid .nm{color:#94514A}
.cfil-row.bau .sq{background:var(--ink-4)} .cfil-row.bau .nm{color:var(--ink-2)}

/* ---------- SECTION 2: STICKY SCROLL HOW IT WORKS ---------- */
.how{padding:132px 0 0}
.how-head{max-width:720px;margin-bottom:8px}
.how-head .eyebrow{display:block;margin-bottom:20px}
.how h2{font-size:clamp(30px,3.8vw,46px);line-height:1.06;letter-spacing:-.032em;font-weight:600;max-width:16ch}
.scroller{display:grid;grid-template-columns:1fr 1.05fr;gap:64px;align-items:start;margin-top:24px}
.steps-col{padding:14vh 0}
.step{padding:36px 0;position:relative;opacity:.4;transition:opacity .4s var(--ease)}
.step.active{opacity:1}
.step .s-n{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--ink-4);margin-bottom:14px;display:flex;align-items:center;gap:12px}
.step .s-n .rail{width:22px;height:1px;background:var(--line);transition:background .4s var(--ease),width .4s var(--ease)}
.step.active .s-n{color:var(--blue)}
.step.active .s-n .rail{background:var(--blue);width:34px}
.step h3{font-size:22px;font-weight:600;letter-spacing:-.022em;line-height:1.2}
.step p{font-size:15.5px;color:var(--ink-2);margin-top:12px;line-height:1.55;max-width:42ch}
.visual-col{position:sticky;top:0;height:100vh;display:flex;align-items:center}
.visual-inner{width:100%}
.vpanel{background:var(--bg);border-radius:14px;box-shadow:var(--hair),0 24px 48px -32px rgba(23,23,23,.16);overflow:hidden}
.vp-bar{padding:13px 18px;box-shadow:0 1px 0 var(--line);display:flex;align-items:center;justify-content:space-between}
.vp-bar .vt{font-size:12.5px;font-weight:550}
.vp-bar .vs{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.08em;color:var(--ink-4);text-transform:uppercase}
.vp-body{padding:18px;min-height:340px;position:relative}
.vstage{position:absolute;inset:18px;opacity:0;transform:translateY(8px);transition:opacity .45s var(--ease),transform .45s var(--ease);pointer-events:none}
.vstage.on{opacity:1;transform:none}
/* stage rows */
.vs-row{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:13px 15px;border-radius:9px;box-shadow:var(--hair);margin-bottom:9px;background:var(--bg);transition:box-shadow .3s var(--ease),background .3s var(--ease)}
.vs-row .vn{font-size:13.5px;font-weight:500;letter-spacing:-.01em}
.vs-row .vsub{font-size:11.5px;color:var(--ink-3);margin-top:3px}
.vs-row .vtag{font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:500;letter-spacing:.05em;padding:3px 8px;border-radius:5px;color:var(--ink-3);background:var(--line-2)}
.vs-row .vtag.test{color:var(--blue-ink);background:var(--blue-wash)}
.vs-row .vtag.act{color:#256B45;background:#EDF5F0}
.vs-row .vtag.avoid{color:#94514A;background:#F7EFEE}
.vs-row.hl{box-shadow:0 0 0 1px var(--blue);background:var(--blue-wash)}
.vs-num{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.vs-num.blue{color:var(--blue-ink)}
.vmeta{display:flex;gap:8px;align-items:center;margin-top:4px;justify-content:flex-end}
.vmeta .m-ebars{display:flex;gap:2.5px}
.vmeta .m-ebars i{width:3.5px;height:10px;border-radius:1px;background:var(--line)}
.vmeta .m-ebars i.on{background:var(--blue)}
.vmeta .m-lbl{font-size:11px;color:var(--ink-3)}
.vs-signal{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--ink-3);display:flex;align-items:center;gap:10px;padding:11px 14px;border-radius:8px;box-shadow:var(--hair);margin-bottom:8px}
.vs-signal .pulse{width:6px;height:6px;border-radius:50%;background:var(--blue);flex:none}
.vs-econ{padding:6px 2px}
.ve-line{display:grid;grid-template-columns:96px 1fr 62px;gap:12px;align-items:center;margin-bottom:12px}
.ve-line:last-child{margin-bottom:0}
.ve-line .ek{font-size:12.5px;color:var(--ink-2)}
.ve-line .etrack{height:6px;border-radius:3px;background:var(--line-2);position:relative;overflow:hidden}
.ve-line .ef{position:absolute;top:0;bottom:0;border-radius:3px}
.ve-line .ef.up{background:var(--ink);left:50%} .ve-line .ef.down{background:var(--ink-4);right:50%} .ve-line .ef.blue{background:var(--blue);left:50%}
.ve-line .ex{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line)}
.ve-line .ev{font-size:12.5px;text-align:right;font-variant-numeric:tabular-nums;font-weight:500}
.ve-line .ev.blue{color:var(--blue-ink)}
.step-progress{display:none}

/* ---------- SECTION 3: DARK TRUST BAND ---------- */
.trust{margin-top:140px;background:var(--dark);color:var(--dark-ink);border-radius:0}
.trust-inner{padding:112px 0}
.trust-grid{display:grid;grid-template-columns:.85fr 1.15fr;gap:80px;align-items:start}
.trust .eyebrow{color:var(--blue);opacity:.9;display:block;margin-bottom:20px}
.trust h2{font-size:clamp(30px,3.6vw,44px);line-height:1.06;letter-spacing:-.03em;font-weight:600;color:#fff;max-width:14ch}
.trust-lead{margin-top:20px;font-size:16px;line-height:1.6;color:var(--dark-ink-2);max-width:42ch}
.trust-table{border-top:1px solid var(--dark-line)}
.tt-row{display:grid;grid-template-columns:150px 1fr;gap:28px;padding:22px 0;border-bottom:1px solid var(--dark-line);align-items:baseline}
.tt-row .k{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--dark-ink-3)}
.tt-row .v{font-size:15px;line-height:1.5;color:var(--dark-ink)}
.tt-row .v b{color:#fff;font-weight:550}

/* ---------- CTA ---------- */
.cta{padding:120px 0}
.cta-inner{text-align:center;max-width:580px;margin:0 auto}
.cta h2{font-size:clamp(30px,3.6vw,44px);line-height:1.06;letter-spacing:-.03em;font-weight:600}
.cta p{margin-top:18px;font-size:17px;color:var(--ink-2);line-height:1.5;max-width:44ch;margin-left:auto;margin-right:auto}
.cta-actions{margin-top:32px;display:flex;gap:11px;justify-content:center;flex-wrap:wrap}
.cta-actions .btn{padding:12px 22px;font-size:15px}
.cta-fine{margin-top:22px;font-size:13px;color:var(--ink-3)}

/* ---------- FOOTER ---------- */
footer{padding:44px 0;box-shadow:0 -1px 0 var(--line)}
.foot{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:18px}
.foot-l{display:flex;align-items:center;gap:12px}
.foot-l .brand{font-size:14px} .foot-l .sep{color:var(--ink-4)} .foot-l .tl{font-size:13px;color:var(--ink-3)}
.foot-r{display:flex;gap:22px}
.foot-r a{font-size:13px;color:var(--ink-3)} .foot-r a:hover{color:var(--ink)}

/* reveal */
.rv{opacity:0;transform:translateY(18px);transition:opacity .55s var(--ease),transform .55s var(--ease)}
.rv.in{opacity:1;transform:none}
.rv[data-d="1"]{transition-delay:.08s}.rv[data-d="2"]{transition-delay:.16s}.rv[data-d="3"]{transition-delay:.24s}

a:focus-visible,.btn:focus-visible,button:focus-visible{outline:2px solid var(--blue);outline-offset:2px;border-radius:6px}

/* ---------- RESPONSIVE ---------- */
@media(max-width:1000px){
  .bento{grid-template-columns:1fr 1fr}
  .tile-wide{grid-row:auto}
}
@media(max-width:900px){
  .drow{grid-template-columns:26px 1fr;grid-template-areas:"stat main""stat econ""stat conf";gap:14px 18px}
  .drow .dstat{grid-area:stat} .drow .dmain{grid-area:main}
  .drow .decon{grid-area:econ;text-align:left;display:flex;align-items:baseline;gap:10px}
  .decon .lbl{margin-top:0} .drow .dconf{grid-area:conf}
  /* sticky scroll → linear stacked on mobile */
  .scroller{grid-template-columns:1fr;gap:0}
  .steps-col{padding:0}
  .visual-col{position:static;height:auto;display:block;margin-top:8px;order:-1}
  .step{opacity:1;padding:28px 0 8px}
  .step.active .s-n .rail{width:22px}
  .mobile-visual{margin:16px 0 40px}
}
@media(max-width:820px){
  .bento{grid-template-columns:1fr}
  .trust-grid{grid-template-columns:1fr;gap:36px}
  .nav-mid,.nav-right{display:none}
  .nav-toggle{display:block;margin-left:auto}
  .m-menu{display:block;position:fixed;inset:82px 0 auto 0;z-index:99;background:rgba(255,255,255,.98);
    backdrop-filter:blur(12px);box-shadow:0 1px 0 var(--line);padding:14px 20px 20px;opacity:0;transform:translateY(-8px);
    pointer-events:none;transition:opacity .2s,transform .2s}
  .m-menu.open{opacity:1;transform:none;pointer-events:auto}
  .m-menu a{display:block;font-size:16px;padding:11px 4px;box-shadow:0 1px 0 var(--line-2)}
  .m-menu .mm-cta{display:flex;flex-direction:column;gap:9px;margin-top:14px}
  .m-menu .mm-cta .btn{justify-content:center;padding:12px}
  .wrap{padding:0 22px}
  .hero{padding:56px 0 0}
  .hero h1{font-size:clamp(52px,15vw,72px);line-height:.92;white-space:normal;max-width:10ch}
  .hero-sub{margin-top:26px;font-size:17px;line-height:1.55}
  .editorial,.how{padding-top:80px}
  .trust-inner{padding:72px 0}
  .cta{padding:80px 0}
  .hero-cta{flex-direction:column;align-items:stretch}.hero-cta .btn{justify-content:center}
  .feed-bar{flex-direction:column;align-items:flex-start;gap:12px}
  .disp-legend{flex-wrap:wrap}
  .tt-row{grid-template-columns:1fr;gap:8px}
}
@media(max-width:680px){
  .wrap{padding-left:18px;padding-right:18px}
  .nav{height:72px}
  .brand{font-size:18px;margin-right:0}
  .m-menu{inset:72px 0 auto 0;padding:12px 18px 18px}

  .hero{padding-top:48px}
  .hero h1{font-size:clamp(44px,13vw,56px);line-height:.94;letter-spacing:-.055em;max-width:8ch}
  .hero-sub{margin-top:22px;font-size:16px;line-height:1.55;max-width:none}
  .hero-cta{margin-top:26px;gap:10px}
  .hero-cta .btn{width:100%;min-height:48px}
  .hero-trust{margin-top:20px;align-items:flex-start;flex-wrap:wrap;gap:7px;font-size:12px;line-height:1.4}

  .product{padding-top:34px}
  .product .wrap{padding-left:10px;padding-right:10px}
  .feed{border-radius:12px;box-shadow:var(--hair),0 18px 45px -34px rgba(23,23,23,.28)}
  .feed-bar{padding:17px 16px;gap:11px}
  .feed-bar-l{display:flex;flex-direction:column;align-items:flex-start;gap:3px}
  .feed-title{font-size:14px}.feed-meta{font-size:12px}
  .disp-legend{gap:5px}.dl{font-size:9px;padding:5px 7px}

  .drow{display:grid;grid-template-columns:1fr;grid-template-areas:"stat" "main" "econ" "conf";gap:16px;padding:22px 18px 24px;align-items:start}
  .drow .dstat{grid-area:stat;display:flex;flex-direction:row;align-items:center;gap:12px}
  .dstat .stag{font-size:10px}.dstat .dcat{font-size:10px}
  .drow .dmain{grid-area:main}.dtitle{font-size:17px}.dsub{font-size:13.5px;line-height:1.5;margin-top:7px;max-width:none}
  .drow .decon{grid-area:econ;display:flex;align-items:baseline;justify-content:space-between;gap:12px;text-align:left;padding-top:14px;border-top:1px solid var(--line-2)}
  .decon .val{font-size:25px}.decon .lbl{font-size:11.5px;text-align:right;margin:0}
  .drow .dconf{grid-area:conf;gap:8px}.dconf .ctop{align-items:center}.dconf .cnum{font-size:15px}
  .feed-foot{padding:15px 16px;flex-direction:column;align-items:flex-start;gap:9px}.feed-foot .fnote{line-height:1.45}

  .editorial{padding-top:88px}.editorial h2{font-size:38px;line-height:1.07;max-width:none}
  .bento{margin-top:38px;gap:12px}.tile{min-height:240px;border-radius:12px}.tile-viz{padding:16px}.tile-cap{padding:18px}
  .crop-row .cr-top{padding:14px;flex-direction:column}.crop-row .cr-val,.crop-row .cr-vlbl{text-align:left}
  .crop-row .cr-econ{padding:0 14px 14px}.cr-line{grid-template-columns:76px 1fr 48px;gap:7px}

  .how{padding-top:88px}.how h2{font-size:38px;max-width:none}.how-sub{font-size:15px}
  .mobile-visual{margin:12px 0 28px}.step{padding:24px 0 6px}.step h3{font-size:18px}.step p{font-size:14px}
  .vpanel{padding:16px}.vpanel-head{gap:8px}.vcard{padding:16px}

  .trust-inner{padding:64px 0}.trust h2{font-size:38px;line-height:1.08}.trust-lead{font-size:15px}
  .tt-row{padding:17px 0}.tt-row .v{font-size:13px;line-height:1.5}

  .cta{padding:68px 0}.cta-inner{padding:34px 20px;border-radius:14px}.cta-inner h2{font-size:34px;line-height:1.08}.cta-inner p{font-size:15px}
  .cta-actions{flex-direction:column}.cta-actions .btn{width:100%;justify-content:center;min-height:48px}
  .cta-fine{font-size:11px}

  footer{padding:34px 0}.foot{align-items:flex-start;flex-direction:column}.foot-l{align-items:flex-start;flex-wrap:wrap}.foot-r{gap:16px;flex-wrap:wrap}
}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition-duration:.01ms!important;scroll-behavior:auto!important}
  .rv{opacity:1;transform:none}
  .step{opacity:1}
}`;

const markup = String.raw`<!-- NAV -->
<header id="hdr">
  <div class="wrap nav">
    <a class="brand" href="#">Exergi</a>
    <nav class="nav-mid" aria-label="Primary">
      <a href="#feed">Product</a>
      <a href="#how">How it works</a>
      <a href="#trust">Trust</a>
    </nav>
    <div class="nav-right">
      <a class="btn btn-ghost" href="#">Sign in</a>
      <a class="btn btn-primary" href="#cta">Join design partners</a>
    </div>
    <button class="nav-toggle" id="navToggle" aria-label="Menu" aria-expanded="false">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3.5 6.5h13M3.5 10h13M3.5 13.5h13" stroke="#171717" stroke-width="1.4" stroke-linecap="round"/></svg>
    </button>
  </div>
  <div class="m-menu" id="mMenu">
    <a href="#feed">Product</a><a href="#how">How it works</a><a href="#trust">Trust</a>
    <div class="mm-cta"><a class="btn btn-secondary" href="#">Sign in</a><a class="btn btn-primary" href="#cta">Join design partners</a></div>
  </div>
</header>

<!-- HERO -->
<section class="hero">
  <div class="wrap">
    <h1>Know what to do next.</h1>
    <p class="hero-sub">Exergi analyzes your commerce data, compares the decisions in front of you, and shows which actions are most likely to increase contribution profit.</p>
    <div class="hero-cta">
      <a class="btn btn-primary" href="#cta">Join design partners <span class="arr">→</span></a>
      <a class="btn btn-secondary" href="#how">See how it works</a>
    </div>
    <div class="hero-trust"><span>Read-only by default</span><span class="dot"></span><span>Evidence behind every recommendation</span></div>
  </div>
</section>

<!-- PRODUCT: DECISION FEED -->
<section class="product" id="feed">
  <div class="wrap">
    <div class="feed rv">
      <div class="feed-bar">
        <div class="feed-bar-l"><span class="feed-title">Decision Feed</span><span class="feed-meta">This week · 3 decisions ready</span></div>
        <div class="disp-legend">
          <span class="dl act"><span class="sq"></span>ACT</span>
          <span class="dl test"><span class="sq"></span>TEST</span>
          <span class="dl avoid"><span class="sq"></span>AVOID</span>
          <span class="dl bau"><span class="sq"></span>BAU</span>
        </div>
      </div>
      <div class="drow rec">
        <div class="drow-accent"></div>
        <div class="dstat"><span class="stag test"><span class="sq"></span>TEST</span><span class="dcat">Shipping</span></div>
        <div class="dmain"><div class="dtitle">Raise free-shipping threshold to $65</div><div class="dsub">Current policy <b>$50</b>. Higher average order value and lower shipping cost outweigh a small dip in conversion.</div></div>
        <div class="decon"><div class="val tnum">+$18,420</div><div class="lbl">Est. contribution profit · 30 days</div></div>
        <div class="dconf rec"><div class="ctop"><span class="cnum">87%</span><span class="clbl">beats BAU</span></div><div class="cbar"><div class="cfill" style="width:87%"></div></div><div class="evi"><span class="ebars"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i></span>Strong evidence</div></div>
      </div>
      <div class="drow">
        <div class="drow-accent"></div>
        <div class="dstat"><span class="stag bau"><span class="sq"></span>BAU</span><span class="dcat">Pricing</span></div>
        <div class="dmain"><div class="dtitle">Keep Core Bundle at $89</div><div class="dsub">Raising to <b>$94</b> could lift profit, but the evidence isn't strong enough to justify the change yet.</div></div>
        <div class="decon"><div class="val flat tnum">±$0</div><div class="lbl">No change recommended</div></div>
        <div class="dconf"><div class="ctop"><span class="cnum">54%</span><span class="clbl">beats BAU</span></div><div class="cbar"><div class="cfill" style="width:54%"></div></div><div class="evi"><span class="ebars"><i class="on"></i><i class="on"></i><i></i><i></i><i></i></span>Limited evidence</div></div>
      </div>
      <div class="drow">
        <div class="drow-accent"></div>
        <div class="dstat"><span class="stag avoid"><span class="sq"></span>AVOID</span><span class="dcat">Offer</span></div>
        <div class="dmain"><div class="dtitle">Skip the 20% win-back discount</div><div class="dsub">Revenue would rise, but the discount cost is larger than the gain — <b>contribution profit falls</b>.</div></div>
        <div class="decon"><div class="val neg tnum">−$7,200</div><div class="lbl">Est. contribution profit · 30 days</div></div>
        <div class="dconf"><div class="ctop"><span class="cnum">81%</span><span class="clbl">worse than BAU</span></div><div class="cbar"><div class="cfill" style="width:81%"></div></div><div class="evi"><span class="ebars"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i></span>Strong evidence</div></div>
      </div>
      <div class="feed-foot"><span class="fnote">Example data · figures are illustrative, not customer results</span><span class="flink">Open a decision →</span></div>
    </div>
  </div>
</section>

<!-- SECTION 1: EDITORIAL + BENTO -->
<section class="editorial" id="evidence">
  <div class="wrap">
    <div class="ed-head">
      <span class="eyebrow rv">Decision intelligence for commerce</span>
      <h2 class="rv" data-d="1">A decision layer for commerce. <span class="muted">Business data becomes clear, economically grounded next actions.</span></h2>
    </div>
    <div class="bento">
      <!-- Tile A (wide) — expanded decision row -->
      <div class="tile tile-wide rv" data-d="1">
        <div class="tile-viz">
          <div class="crop-row">
            <div class="cr-top">
              <div><div class="cr-stat"><span class="sq"></span>TEST · SHIPPING</div><div class="cr-title">Raise free-shipping<br>threshold to $65</div></div>
              <div><div class="cr-val">+$18,420</div><div class="cr-vlbl">Contribution profit · 30d</div></div>
            </div>
            <div class="cr-econ">
              <div class="cr-line"><span class="ck">Conversion</span><span class="ctrack"><span class="cx"></span><span class="cf down" style="width:9%"></span></span><span class="cv">−0.4%</span></div>
              <div class="cr-line"><span class="ck">AOV</span><span class="ctrack"><span class="cx"></span><span class="cf up" style="width:20%"></span></span><span class="cv">+$4.70</span></div>
              <div class="cr-line"><span class="ck">Shipping</span><span class="ctrack"><span class="cx"></span><span class="cf up" style="width:24%"></span></span><span class="cv">+$9.8k</span></div>
              <div class="cr-line"><span class="ck">Contribution</span><span class="ctrack"><span class="cx"></span><span class="cf blue" style="width:36%"></span></span><span class="cv blue">+$18.4k</span></div>
            </div>
          </div>
        </div>
        <div class="tile-cap"><div class="k">Fig. 01 · A decision, priced</div><div class="t">Find the decisions that matter</div><div class="d">Every candidate is priced in contribution profit — not revenue alone.</div></div>
      </div>
      <!-- Tile B — evidence -->
      <div class="tile rv" data-d="2">
        <div class="tile-viz">
          <div class="crop-evi">
            <div class="ce-h"><span class="ce-t">Why this beats BAU</span><span class="ce-pct">87%</span></div>
            <div class="ce-row"><span class="k">Sample</span><span class="v">41,280 orders</span></div>
            <div class="ce-row"><span class="k">Downside case</span><span class="v">still &gt; BAU</span></div>
            <div class="ce-row"><span class="k">Evidence</span><span class="ce-ebars"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i></span></div>
          </div>
        </div>
        <div class="tile-cap"><div class="k">Fig. 02 · Evidence</div><div class="t">See the confidence, not a score</div></div>
      </div>
      <!-- Tile C — status filter -->
      <div class="tile rv" data-d="3">
        <div class="tile-viz">
          <div class="crop-filter">
            <div class="cfil-row act"><span class="sq"></span><span class="nm">ACT</span><span class="ct">2</span></div>
            <div class="cfil-row test"><span class="sq"></span><span class="nm">TEST</span><span class="ct">1</span></div>
            <div class="cfil-row avoid"><span class="sq"></span><span class="nm">AVOID</span><span class="ct">1</span></div>
            <div class="cfil-row bau"><span class="sq"></span><span class="nm">BAU</span><span class="ct">4</span></div>
          </div>
        </div>
        <div class="tile-cap"><div class="k">Fig. 03 · Dispositions</div><div class="t">One clear call per decision</div></div>
      </div>
    </div>
  </div>
</section>

<!-- SECTION 2: STICKY SCROLL HOW IT WORKS -->
<section class="how" id="how">
  <div class="wrap">
    <div class="how-head">
      <span class="eyebrow rv">How it works</span>
      <h2 class="rv" data-d="1">From raw commerce data to a decision you can defend.</h2>
    </div>
    <div class="scroller">
      <!-- pinned visual -->
      <div class="visual-col">
        <div class="visual-inner">
          <div class="vpanel">
            <div class="vp-bar"><span class="vt">Decision Feed</span><span class="vs" id="vp-stage-label">Ingesting signals</span></div>
            <div class="vp-body">
              <!-- stage 1: signals -->
              <div class="vstage on" data-stage="0">
                <div class="vs-signal"><span class="pulse"></span>orders · 41,280 rows synced</div>
                <div class="vs-signal"><span class="pulse"></span>margins · unit economics mapped</div>
                <div class="vs-signal"><span class="pulse"></span>shipping · cost per order joined</div>
                <div class="vs-signal"><span class="pulse"></span>promotions · discount history read</div>
              </div>
              <!-- stage 2: candidates found -->
              <div class="vstage" data-stage="1">
                <div class="vs-row"><div><div class="vn">Raise free-shipping threshold</div><div class="vsub">Shipping</div></div><span class="vs-num tnum">high value</span></div>
                <div class="vs-row"><div><div class="vn">Core Bundle price</div><div class="vsub">Pricing</div></div><span class="vs-num tnum" style="color:var(--ink-3)">review</span></div>
                <div class="vs-row"><div><div class="vn">Win-back discount</div><div class="vsub">Offer</div></div><span class="vs-num tnum" style="color:var(--ink-3)">review</span></div>
              </div>
              <!-- stage 3: compare vs BAU -->
              <div class="vstage" data-stage="2">
                <div class="vs-row"><div><div class="vn">$50 · BAU</div></div><span class="vs-num tnum" style="color:var(--ink-3)">$91.2k</span></div>
                <div class="vs-row"><div><div class="vn">$60</div></div><span class="vs-num tnum">$97.1k</span></div>
                <div class="vs-row hl"><div><div class="vn">$65</div></div><span class="vs-num blue tnum">$109.6k</span></div>
                <div class="vs-row"><div><div class="vn">$75</div></div><span class="vs-num tnum">$101.8k</span></div>
              </div>
              <!-- stage 4: economics -->
              <div class="vstage" data-stage="3">
                <div class="vs-econ">
                  <div class="ve-line"><span class="ek">Conversion</span><span class="etrack"><span class="ex"></span><span class="ef down" style="width:9%"></span></span><span class="ev">−0.4%</span></div>
                  <div class="ve-line"><span class="ek">AOV</span><span class="etrack"><span class="ex"></span><span class="ef up" style="width:20%"></span></span><span class="ev">+$4.70</span></div>
                  <div class="ve-line"><span class="ek">Shipping cost</span><span class="etrack"><span class="ex"></span><span class="ef up" style="width:24%"></span></span><span class="ev">+$9.8k</span></div>
                  <div class="ve-line"><span class="ek">Contribution</span><span class="etrack"><span class="ex"></span><span class="ef blue" style="width:36%"></span></span><span class="ev blue">+$18.4k</span></div>
                </div>
              </div>
              <!-- stage 5: disposition -->
              <div class="vstage" data-stage="4">
                <div class="vs-row hl"><div><div class="vn">Raise free-shipping threshold to $65</div><div class="vsub">Shipping · 30-day window</div></div><span class="vtag test">TEST</span></div>
                <div class="vs-row"><div><div class="vn">Est. contribution profit</div></div><span class="vs-num blue tnum">+$18,420</span></div>
                <div class="vs-row"><div><div class="vn">Probability of beating BAU</div><div class="vmeta"><span class="m-ebars"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i></span><span class="m-lbl">strong</span></div></div><span class="vs-num tnum">87%</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- steps -->
      <div class="steps-col">
        <div class="step" data-step="0">
          <div class="s-n"><span class="rail"></span>01</div><h3>Connect the economic picture</h3>
          <p>Orders, margins, shipping and promotions are read into one decision context — read-only.</p>
        </div>
        <div class="step" data-step="1">
          <div class="s-n"><span class="rail"></span>02</div><h3>Find the decisions that matter</h3>
          <p>Exergi surfaces the pricing, shipping and offer decisions where a change is actually worth considering.</p>
        </div>
        <div class="step" data-step="2">
          <div class="s-n"><span class="rail"></span>03</div><h3>Compare actions against BAU</h3>
          <p>Each candidate action competes with your current policy — not a vanity forecast.</p>
        </div>
        <div class="step" data-step="3">
          <div class="s-n"><span class="rail"></span>04</div><h3>Price it in contribution profit</h3>
          <p>See the trade-off across conversion, AOV and cost — resolved to the number that reaches the bottom line.</p>
        </div>
        <div class="step" data-step="4">
          <div class="s-n"><span class="rail"></span>05</div><h3>Decide: act, test, avoid or hold</h3>
          <p>One clear call, with the probability it beats BAU and the strength of the evidence behind it.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- SECTION 3: DARK TRUST BAND -->
<section class="trust" id="trust">
  <div class="wrap trust-inner">
    <div class="trust-grid">
      <div>
        <span class="eyebrow rv">Built for trust</span>
        <h2 class="rv" data-d="1">A recommendation is not an order.</h2>
        <p class="trust-lead rv" data-d="2">Exergi is built for decisions that move real economics. It shows its working and leaves the business in control.</p>
      </div>
      <div class="trust-table rv" data-d="1">
        <div class="tt-row"><span class="k">Control</span><span class="v"><b>Read-only by default.</b> No autonomous changes to your store.</span></div>
        <div class="tt-row"><span class="k">Evidence</span><span class="v">Every recommendation links to the data, sample and baseline behind it.</span></div>
        <div class="tt-row"><span class="k">Uncertainty</span><span class="v">Probability and downside are shown explicitly — never hidden behind one score.</span></div>
        <div class="tt-row"><span class="k">Human</span><span class="v">You decide what to act on, test, or leave unchanged.</span></div>
        <div class="tt-row"><span class="k">Security</span><span class="v">Encrypted in transit and at rest · scoped, revocable access · SOC 2 in progress.</span></div>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="cta" id="cta">
  <div class="wrap">
    <div class="cta-inner rv">
      <h2>Evaluate Exergi on your own store data.</h2>
      <p>We're working with a small group of US commerce brands as design partners. Read-only connection, no autonomous changes.</p>
      <div class="cta-actions">
        <a class="btn btn-primary" href="#">Join design partners <span class="arr">→</span></a>
        <a class="btn btn-secondary" href="#">Talk to the team</a>
      </div>
      <div class="cta-fine">Selective intake · US commerce brands</div>
    </div>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="wrap foot">
    <div class="foot-l"><a class="brand" href="#">Exergi</a><span class="sep">·</span><span class="tl">Decision intelligence for commerce</span></div>
    <div class="foot-r"><a href="#how">Product</a><a href="#cta">Design partners</a><a href="#">Privacy</a><a href="#">Terms</a></div>
  </div>
</footer>`;

export default function Home() {
  useEffect(() => {
    const header = document.getElementById("hdr");
    const navToggle = document.getElementById("navToggle");
    const mobileMenu = document.getElementById("mMenu");
    const steps = Array.from(document.querySelectorAll<HTMLElement>(".step"));
    const stages = Array.from(
      document.querySelectorAll<HTMLElement>(".vstage"),
    );
    const stageLabel = document.getElementById("vp-stage-label");
    const stageLabels = [
      "Ingesting signals",
      "Candidates found",
      "Compare vs BAU",
      "Economics",
      "Recommendation",
    ];

    const onScroll = () =>
      header?.classList.toggle("scrolled", window.scrollY > 6);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    const onToggle = () => {
      if (!mobileMenu || !navToggle) return;
      const open = mobileMenu.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", String(open));
    };
    navToggle?.addEventListener("click", onToggle);

    const menuLinks = Array.from(mobileMenu?.querySelectorAll("a") ?? []);
    const closeMenu = () => {
      mobileMenu?.classList.remove("open");
      navToggle?.setAttribute("aria-expanded", "false");
    };
    menuLinks.forEach((link) => link.addEventListener("click", closeMenu));

    const revealObserver = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealObserver.unobserve(entry.target);
          }
        }),
      { threshold: 0.12 },
    );
    document
      .querySelectorAll(".rv")
      .forEach((element) => revealObserver.observe(element));

    const setActive = (index: number) => {
      steps.forEach((step) =>
        step.classList.toggle("active", Number(step.dataset.step) === index),
      );
      stages.forEach((stage) =>
        stage.classList.toggle("on", Number(stage.dataset.stage) === index),
      );
      if (stageLabel) stageLabel.textContent = stageLabels[index] ?? "";
    };

    let stepObserver: IntersectionObserver | undefined;
    if (window.matchMedia("(max-width:900px)").matches) {
      steps.forEach((step) => step.classList.add("active"));
    } else {
      stepObserver = new IntersectionObserver(
        (entries) =>
          entries.forEach((entry) => {
            if (entry.isIntersecting)
              setActive(Number((entry.target as HTMLElement).dataset.step));
          }),
        { rootMargin: "-50% 0px -49% 0px", threshold: 0 },
      );
      steps.forEach((step) => stepObserver?.observe(step));
      setActive(0);
    }

    return () => {
      window.removeEventListener("scroll", onScroll);
      navToggle?.removeEventListener("click", onToggle);
      menuLinks.forEach((link) => link.removeEventListener("click", closeMenu));
      revealObserver.disconnect();
      stepObserver?.disconnect();
    };
  }, []);

  return (
    <>
      <style>{styles}</style>
      <div dangerouslySetInnerHTML={{ __html: markup }} />
    </>
  );
}
