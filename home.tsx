const styles = `
:root{
  --bg:#ffffff;
  --ink:#0f1115;
  --muted:#6f7682;
  --muted-2:#9aa1ac;
  --line:#eceef2;
  --panel:#fbfbfc;
  --soft:#f5f7fa;
  --blue:#3b63ff;
  --blue-soft:#eef2ff;
  --green:#127a42;
  --green-soft:#ecf8f1;
  --red:#b42318;
  --red-soft:#fff1f0;
  --shadow:0 30px 90px rgba(15,17,21,.08), 0 8px 24px rgba(15,17,21,.05);
  --radius:22px;
  --max:1320px;
}

*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  background:var(--bg);
  color:var(--ink);
  font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
}
a{color:inherit;text-decoration:none}
button,input{font:inherit}

.ex-wrap{
  width:min(var(--max),calc(100% - 56px));
  margin:0 auto;
}

.ex-line{
  height:1px;
  background:var(--line);
}

/* NAV */
.ex-nav{
  height:72px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:24px;
}
.ex-brand{
  font-size:18px;
  font-weight:650;
  letter-spacing:-.03em;
}
.ex-nav-center,
.ex-nav-right{
  display:flex;
  align-items:center;
  gap:30px;
}
.ex-nav-center a,
.ex-nav-right a{
  font-size:14px;
  font-weight:500;
  color:#666c76;
  transition:color .18s ease;
}
.ex-nav-center a:hover,
.ex-nav-right a:hover{
  color:var(--ink);
}
.ex-nav-cta{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:10px 16px;
  border-radius:12px;
  border:1px solid #111214;
  background:#111214;
  color:#fff !important;
  font-size:14px;
  font-weight:600 !important;
  transition:transform .18s ease, background .18s ease;
}
.ex-nav-cta:hover{
  transform:translateY(-1px);
  background:#22242a;
}
.ex-arrow{font-size:16px;line-height:1}

/* HERO */
.ex-hero{
  padding:120px 0 72px;
}
.ex-hero-inner{
  max-width:980px;
}
.ex-h1{
  margin:0;
  max-width:980px;
  font-size:clamp(60px,8vw,104px);
  line-height:.94;
  font-weight:590;
  letter-spacing:-.07em;
}
.ex-hero-copy{
  margin:28px 0 0;
  max-width:620px;
  color:var(--muted);
  font-size:18px;
  line-height:1.6;
  letter-spacing:-.02em;
}
.ex-hero-actions{
  margin-top:30px;
  display:flex;
  align-items:center;
  gap:22px;
  flex-wrap:wrap;
}
.ex-primary{
  display:inline-flex;
  align-items:center;
  gap:10px;
  padding:14px 18px;
  border-radius:12px;
  border:1px solid #111214;
  background:#111214;
  color:#fff;
  font-size:14px;
  font-weight:600;
  transition:transform .18s ease, background .18s ease;
}
.ex-primary:hover{
  transform:translateY(-1px);
  background:#22242a;
}
.ex-text-link{
  display:inline-flex;
  align-items:center;
  gap:8px;
  color:#4b5059;
  font-size:14px;
  font-weight:600;
}
.ex-text-link:hover{color:var(--ink)}

/* PRODUCT STAGE */
.ex-stage{
  padding:8px 0 130px;
}
.ex-shell{
  overflow:hidden;
  border:1px solid #cfd4dc;
  border-radius:24px;
  background:#fff;
  box-shadow:var(--shadow);
}
.ex-chrome{
  height:48px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:0 18px;
  border-bottom:1px solid var(--line);
  background:linear-gradient(#fff,#fcfcfd);
}
.ex-chrome-left,
.ex-chrome-right{
  display:flex;
  align-items:center;
  gap:10px;
}
.ex-dots{
  display:flex;
  gap:6px;
}
.ex-dots span{
  width:8px;
  height:8px;
  border-radius:999px;
  background:#d6d9de;
}
.ex-chrome-title{
  color:#9499a2;
  font-size:12px;
}
.ex-pill{
  padding:5px 9px;
  border:1px solid var(--line);
  border-radius:999px;
  background:#fff;
  color:#757b84;
  font-size:11px;
}

.ex-app{
  min-height:660px;
  display:grid;
  grid-template-columns:220px 1fr;
}

.ex-sidebar{
  padding:22px 16px 18px;
  border-right:1px solid #d4d8df;
  background:#fcfcfd;
}
.ex-sidebar-brand{
  margin:2px 10px 24px;
  font-size:14px;
  font-weight:650;
}
.ex-side-label{
  margin:18px 10px 8px;
  color:#a3a8b0;
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
}
.ex-side-item{
  height:40px;
  display:flex;
  align-items:center;
  margin:2px 0;
  padding:0 10px;
  border-radius:10px;
  color:#6e747e;
  font-size:13px;
}
.ex-side-item.active{
  background:#f2f5f8;
  color:#111214;
  font-weight:600;
}
.ex-main{
  padding:32px 32px 36px;
}
.ex-main-top{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:24px;
  margin-bottom:24px;
}
.ex-eyebrow{
  margin-bottom:8px;
  color:#9ba0a8;
  font-size:11px;
  font-weight:600;
  letter-spacing:.08em;
  text-transform:uppercase;
}
.ex-main-title{
  margin:0;
  font-size:24px;
  font-weight:630;
  letter-spacing:-.03em;
}
.ex-main-sub{
  margin:6px 0 0;
  color:#7d838c;
  font-size:13px;
}
.ex-tabs{
  display:flex;
  gap:6px;
  padding:4px;
  border-radius:10px;
  background:#f5f6f8;
}
.ex-tab{
  padding:7px 10px;
  border-radius:8px;
  color:#8b919a;
  font-size:11px;
  font-weight:600;
}
.ex-tab.active{
  background:#fff;
  color:#111214;
  box-shadow:0 1px 2px rgba(17,18,20,.06);
}

.ex-list{
  overflow:hidden;
  border:1px solid var(--line);
  border-radius:16px;
}
.ex-row{
  position:relative;
  display:grid;
  grid-template-columns:1.55fr .5fr .5fr;
  gap:24px;
  padding:25px 24px;
  border-bottom:1px solid var(--line);
  background:#fff;
}
.ex-row:last-of-type{border-bottom:none}
.ex-row.featured::before{
  content:"";
  position:absolute;
  left:-1px;
  top:0;
  bottom:0;
  width:2px;
  background:var(--blue);
}
.ex-row-kicker{
  display:flex;
  align-items:center;
  gap:10px;
  margin-bottom:11px;
  color:#a2a7af;
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
}
.ex-row h3{
  margin:0 0 8px;
  font-size:16px;
  line-height:1.35;
  font-weight:630;
  letter-spacing:-.02em;
}
.ex-row p{
  max-width:560px;
  margin:0;
  color:#7a8088;
  font-size:12.5px;
  line-height:1.56;
}
.ex-badge{
  display:inline-flex;
  align-items:center;
  padding:4px 7px;
  border-radius:7px;
  font-size:10px;
  font-weight:750;
  letter-spacing:.04em;
}
.ex-badge.test{background:var(--blue-soft);color:var(--blue)}
.ex-badge.bau{background:#f1f2f4;color:#737983}
.ex-badge.avoid{background:var(--red-soft);color:var(--red)}

.ex-metric,
.ex-confidence{
  align-self:center;
}
.ex-metric-big{
  white-space:nowrap;
  font-size:22px;
  font-weight:680;
  letter-spacing:-.04em;
}
.ex-metric-label{
  margin-top:4px;
  color:#9ca1a9;
  font-size:10.5px;
  line-height:1.35;
}
.ex-confidence-top{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
}
.ex-confidence-num{
  font-size:15px;
  font-weight:700;
}
.ex-confidence-small{
  color:#a3a8b0;
  font-size:10px;
}
.ex-bar{
  height:4px;
  margin-top:8px;
  overflow:hidden;
  border-radius:999px;
  background:#eceef1;
}
.ex-bar span{
  display:block;
  height:100%;
  border-radius:999px;
}
.ex-evidence{
  display:flex;
  align-items:center;
  gap:8px;
  margin-top:10px;
  color:#8e949c;
  font-size:10px;
}
.ex-bars{
  height:10px;
  display:flex;
  align-items:flex-end;
  gap:2px;
}
.ex-bars i{
  display:block;
  width:2px;
  border-radius:999px;
  background:#cfd3d9;
}
.ex-bars i:nth-child(1){height:4px}
.ex-bars i:nth-child(2){height:6px}
.ex-bars i:nth-child(3){height:8px}
.ex-bars i:nth-child(4){height:10px}
.ex-footer-row{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  padding:17px 24px;
  background:#fbfbfc;
  color:#9398a1;
  font-size:11px;
}
.ex-footer-row a{
  color:#464b53;
  font-weight:600;
}

/* BIG TEXT SECTION */
.ex-editorial{
  padding:130px 0 136px;
  border-top:1px solid var(--line);
}
.ex-editorial h2{
  max-width:1040px;
  margin:0;
  font-size:clamp(42px,4.8vw,74px);
  line-height:1.08;
  font-weight:560;
  letter-spacing:-.05em;
}
.ex-editorial h2 .muted{
  color:#a2a7af;
}
.ex-figures{
  margin-top:100px;
  display:grid;
  grid-template-columns:repeat(3,1fr);
  border-top:1px solid var(--line);
  border-bottom:1px solid var(--line);
}
.ex-figure{
  min-height:340px;
  padding:28px 34px 36px 0;
}
.ex-figure + .ex-figure{
  padding-left:34px;
  border-left:1px solid var(--line);
}
.ex-fig-label{
  margin-bottom:42px;
  color:#b0b4bb;
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
}
.ex-diagram{
  height:150px;
  display:grid;
  place-items:center;
  margin-bottom:34px;
  color:#c9cdd3;
}
.ex-diagram svg{
  width:100%;
  max-width:220px;
  height:150px;
}
.ex-figure h3{
  margin:0 0 10px;
  font-size:15px;
  letter-spacing:-.015em;
}
.ex-figure p{
  max-width:330px;
  margin:0;
  color:#7d838c;
  font-size:13px;
  line-height:1.6;
}

/* HOW */
.ex-section{
  padding:124px 0;
  border-top:1px solid var(--line);
}
.ex-section-head{
  display:grid;
  grid-template-columns:.7fr 1.3fr;
  gap:60px;
  align-items:start;
  margin-bottom:70px;
}
.ex-section-num{
  color:#a3a8b0;
  font-size:11px;
  letter-spacing:.13em;
  text-transform:uppercase;
}
.ex-section h2,
.ex-trust h2{
  max-width:860px;
  margin:0;
  font-size:clamp(38px,4vw,64px);
  line-height:1.06;
  font-weight:570;
  letter-spacing:-.05em;
}
.ex-flow{
  display:grid;
  grid-template-columns:repeat(5,1fr);
  overflow:hidden;
  border:1px solid var(--line);
  border-radius:18px;
  background:#fff;
}
.ex-step{
  min-height:190px;
  padding:28px 24px 30px;
}
.ex-step + .ex-step{
  border-left:1px solid var(--line);
}
.ex-step-index{
  margin-bottom:44px;
  color:#a5aab2;
  font-size:10px;
}
.ex-step strong{
  display:block;
  margin-bottom:9px;
  font-size:14px;
  letter-spacing:-.01em;
}
.ex-step p{
  margin:0;
  color:#7d838c;
  font-size:12px;
  line-height:1.56;
}

/* TRUST */
.ex-trust{
  padding:124px 0 132px;
  border-top:1px solid var(--line);
}
.ex-trust-grid{
  display:grid;
  grid-template-columns:1.05fr .95fr;
  gap:100px;
  align-items:start;
}
.ex-trust h2{
  margin:0 0 24px;
}
.ex-trust-copy{
  max-width:600px;
  margin:0;
  color:#727883;
  font-size:16px;
  line-height:1.65;
}
.ex-trust-list{
  border-top:1px solid var(--line);
}
.ex-trust-row{
  display:grid;
  grid-template-columns:120px 1fr;
  gap:24px;
  padding:22px 0;
  border-bottom:1px solid var(--line);
}
.ex-trust-row span{
  color:#a4a8b0;
  font-size:11px;
  letter-spacing:.08em;
  text-transform:uppercase;
}
.ex-trust-row strong{
  font-size:14px;
  font-weight:600;
  line-height:1.45;
}

/* CTA */
.ex-final{
  padding:120px 0 84px;
  border-top:1px solid var(--line);
}
.ex-final-box{
  display:flex;
  align-items:end;
  justify-content:space-between;
  gap:60px;
  padding:68px;
  border:1px solid var(--line);
  border-radius:24px;
  background:linear-gradient(180deg,#fff,#fafbfc);
}
.ex-final h2{
  max-width:680px;
  margin:0;
  font-size:48px;
  line-height:1.06;
  font-weight:570;
  letter-spacing:-.045em;
}
.ex-final p{
  max-width:620px;
  margin:18px 0 0;
  color:#7c8189;
  font-size:15px;
  line-height:1.6;
}
.ex-site-footer{
  display:flex;
  justify-content:space-between;
  gap:30px;
  padding:28px 0 40px;
  color:#9ba0a8;
  font-size:12px;
}
.ex-site-footer-links{
  display:flex;
  gap:20px;
}

/* RESPONSIVE */
@media (max-width:980px){
  .ex-nav-center{display:none}
  .ex-app{grid-template-columns:1fr}
  .ex-sidebar{display:none}
  .ex-figures{grid-template-columns:1fr}
  .ex-figure + .ex-figure{
    padding-left:0;
    border-left:none;
    border-top:1px solid var(--line);
  }
  .ex-section-head,
  .ex-trust-grid{
    grid-template-columns:1fr;
    gap:34px;
  }
  .ex-flow{grid-template-columns:1fr}
  .ex-step + .ex-step{
    border-left:none;
    border-top:1px solid var(--line);
  }
  .ex-row{grid-template-columns:1fr;gap:18px}
  .ex-final-box{
    flex-direction:column;
    align-items:flex-start;
  }
}
@media (max-width:640px){
  .ex-wrap{width:min(100% - 32px,var(--max))}
  .ex-nav{height:64px}
  .ex-nav-right .ex-signin{display:none}
  .ex-nav-cta{padding:9px 11px}
  .ex-hero{padding:88px 0 56px}
  .ex-h1{font-size:54px}
  .ex-hero-copy{font-size:16px;margin-top:24px}
  .ex-stage{padding-bottom:88px}
  .ex-main{padding:20px 16px 24px}
  .ex-tabs{display:none}
  .ex-row{padding:21px 18px}
  .ex-editorial,
  .ex-section,
  .ex-trust{padding:88px 0}
  .ex-editorial h2,
  .ex-section h2,
  .ex-trust h2{font-size:40px}
  .ex-figures{margin-top:72px}
  .ex-final{padding:88px 0 56px}
  .ex-final-box{padding:36px 28px}
  .ex-final h2{font-size:38px}
  .ex-site-footer{flex-direction:column}
}
`;

function EvidenceBars({ accent = "#3b63ff" }: { accent?: string }) {
  return (
    <span className="ex-bars" aria-hidden="true">
      <i />
      <i />
      <i />
      <i style={{ background: accent }} />
    </span>
  );
}

export default function Home() {
  return (
    <>
      <style>{styles}</style>

      <header>
        <div className="ex-wrap ex-nav">
          <a className="ex-brand" href="#">
            Exergi
          </a>

          <nav className="ex-nav-center" aria-label="Primary">
            <a href="#product">Product</a>
            <a href="#how">How it works</a>
            <a href="#evidence">Evidence</a>
            <a href="#research">Research</a>
          </nav>

          <div className="ex-nav-right">
            <a className="ex-signin" href="#">
              Sign in
            </a>
            <a className="ex-nav-cta" href="#partners">
              Join design partners <span className="ex-arrow">→</span>
            </a>
          </div>
        </div>
        <div className="ex-line" />
      </header>

      <main>
        <section className="ex-hero">
          <div className="ex-wrap">
            <div className="ex-hero-inner">
              <h1 className="ex-h1">Know what to do next.</h1>

              <p className="ex-hero-copy">
                Exergi analyzes your commerce data, compares the decisions in
                front of you, and shows which actions are most likely to
                increase contribution profit.
              </p>

              <div className="ex-hero-actions">
                <a className="ex-primary" href="#partners">
                  Join design partners <span className="ex-arrow">→</span>
                </a>
                <a className="ex-text-link" href="#product">
                  See the product <span>↘</span>
                </a>
              </div>
            </div>
          </div>
        </section>

        <section className="ex-stage" id="product">
          <div className="ex-wrap">
            <div className="ex-shell">
              <div className="ex-chrome">
                <div className="ex-chrome-left">
                  <div className="ex-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className="ex-chrome-title">Exergi · Decision Feed</div>
                </div>

                <div className="ex-chrome-right">
                  <span className="ex-pill">Read-only</span>
                  <span className="ex-pill">Example data</span>
                </div>
              </div>

              <div className="ex-app">
                <aside className="ex-sidebar">
                  <div className="ex-sidebar-brand">Exergi</div>

                  <div className="ex-side-label">Workspace</div>
                  <div className="ex-side-item active">
                    Decision Feed
                  </div>
                  <div className="ex-side-item">
                    Ask Exergi
                  </div>
                  <div className="ex-side-item">
                    Experiments
                  </div>
                  <div className="ex-side-item">
                    Evidence
                  </div>
                  <div className="ex-side-item">
                    Economics
                  </div>

                  <div className="ex-side-label">Account</div>
                  <div className="ex-side-item">
                    Data sources
                  </div>
                  <div className="ex-side-item">
                    Settings
                  </div>
                </aside>

                <section className="ex-main">
                  <div className="ex-main-top">
                    <div>
                      <div className="ex-eyebrow">Decision Feed</div>
                      <h2 className="ex-main-title">Three decisions ready</h2>
                      <p className="ex-main-sub">
                        Ranked by expected contribution-profit opportunity and
                        evidence.
                      </p>
                    </div>

                    <div className="ex-tabs">
                      <span className="ex-tab active">Ready</span>
                      <span className="ex-tab">In test</span>
                      <span className="ex-tab">Concluded</span>
                    </div>
                  </div>

                  <div className="ex-list">
                    <article className="ex-row featured">
                      <div>
                        <div className="ex-row-kicker">
                          Shipping
                          <span className="ex-badge test">TEST</span>
                        </div>
                        <h3>Raise free-shipping threshold to $65</h3>
                        <p>
                          Current policy is $50. Higher average order value and
                          lower shipping cost are expected to outweigh a small
                          conversion decline.
                        </p>
                      </div>

                      <div className="ex-metric">
                        <div className="ex-metric-big">+$18,420</div>
                        <div className="ex-metric-label">
                          Est. contribution profit
                          <br />
                          30 days
                        </div>
                      </div>

                      <div className="ex-confidence">
                        <div className="ex-confidence-top">
                          <span className="ex-confidence-num">87%</span>
                          <span className="ex-confidence-small">beats BAU</span>
                        </div>
                        <div className="ex-bar">
                          <span style={{ width: "87%", background: "#3b63ff" }} />
                        </div>
                        <div className="ex-evidence">
                          <EvidenceBars />
                          Strong evidence
                        </div>
                      </div>
                    </article>

                    <article className="ex-row">
                      <div>
                        <div className="ex-row-kicker">
                          Pricing
                          <span className="ex-badge bau">BAU</span>
                        </div>
                        <h3>Keep Core Bundle at $89</h3>
                        <p>
                          Raising to $94 could improve profit, but the evidence
                          is not strong enough to justify a change today.
                        </p>
                      </div>

                      <div className="ex-metric">
                        <div className="ex-metric-big">±$0</div>
                        <div className="ex-metric-label">
                          No change
                          <br />
                          recommended
                        </div>
                      </div>

                      <div className="ex-confidence">
                        <div className="ex-confidence-top">
                          <span className="ex-confidence-num">54%</span>
                          <span className="ex-confidence-small">beats BAU</span>
                        </div>
                        <div className="ex-bar">
                          <span style={{ width: "54%", background: "#a7adb6" }} />
                        </div>
                        <div className="ex-evidence">
                          <EvidenceBars accent="#cfd3d9" />
                          Limited evidence
                        </div>
                      </div>
                    </article>

                    <article className="ex-row">
                      <div>
                        <div className="ex-row-kicker">
                          Offer
                          <span className="ex-badge avoid">AVOID</span>
                        </div>
                        <h3>Avoid 20% win-back discount</h3>
                        <p>
                          Revenue may increase, but modeled margin compression
                          makes contribution profit more likely to decline.
                        </p>
                      </div>

                      <div className="ex-metric">
                        <div className="ex-metric-big">−$3,780</div>
                        <div className="ex-metric-label">
                          Est. contribution profit
                          <br />
                          30 days
                        </div>
                      </div>

                      <div className="ex-confidence">
                        <div className="ex-confidence-top">
                          <span className="ex-confidence-num">21%</span>
                          <span className="ex-confidence-small">beats BAU</span>
                        </div>
                        <div className="ex-bar">
                          <span style={{ width: "21%", background: "#c43b32" }} />
                        </div>
                        <div className="ex-evidence">
                          <EvidenceBars accent="#c43b32" />
                          Negative economics
                        </div>
                      </div>
                    </article>

                    <div className="ex-footer-row">
                      <span>
                        Recommendations are read-only. You stay in control.
                      </span>
                      <a href="#how">How decisions are made →</a>
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </div>
        </section>

        <section className="ex-editorial" id="evidence">
          <div className="ex-wrap">
            <h2>
              A decision layer for commerce.{" "}
              <span className="muted">
                Built to turn business data into clear, economically grounded
                next actions.
              </span>
            </h2>

            <div className="ex-figures">
              <article className="ex-figure">
                <div className="ex-fig-label">Fig 0.1</div>
                <div className="ex-diagram">
                  <svg viewBox="0 0 240 160" fill="none" stroke="currentColor" strokeWidth="1.15">
                    <rect x="39" y="35" width="162" height="88" rx="8" />
                    <rect x="55" y="52" width="130" height="55" rx="6" />
                    <path d="M72 69h96M72 82h64M72 95h78" />
                    <circle cx="49" cy="79" r="3" />
                  </svg>
                </div>
                <h3>Find the decisions that matter</h3>
                <p>
                  Surface high-value decision opportunities instead of adding
                  another dashboard to monitor.
                </p>
              </article>

              <article className="ex-figure">
                <div className="ex-fig-label">Fig 0.2</div>
                <div className="ex-diagram">
                  <svg viewBox="0 0 240 160" fill="none" stroke="currentColor" strokeWidth="1.15">
                    <rect x="22" y="82" width="56" height="42" rx="7" />
                    <rect x="92" y="36" width="56" height="42" rx="7" />
                    <rect x="162" y="82" width="56" height="42" rx="7" />
                    <path d="M78 103h30M132 78v22M148 57h20M120 78v23M108 103H78M132 103h30" />
                  </svg>
                </div>
                <h3>Compare actions against BAU</h3>
                <p>
                  Every alternative is evaluated against what the business
                  would otherwise keep doing.
                </p>
              </article>

              <article className="ex-figure">
                <div className="ex-fig-label">Fig 0.3</div>
                <div className="ex-diagram">
                  <svg viewBox="0 0 240 160" fill="none" stroke="currentColor" strokeWidth="1.15">
                    <path d="M33 121l39-40 31 23 44-62 58 47" />
                    <path d="M33 124h172M33 35v89" />
                    <circle cx="147" cy="42" r="4" />
                    <path d="M147 42v48" strokeDasharray="3 4" />
                  </svg>
                </div>
                <h3>Understand the economics before acting</h3>
                <p>
                  See expected contribution profit, uncertainty, evidence, and
                  what could change the recommendation.
                </p>
              </article>
            </div>
          </div>
        </section>

        <section className="ex-section" id="how">
          <div className="ex-wrap">
            <div className="ex-section-head">
              <div className="ex-section-num">01 · How Exergi works</div>
              <h2>From raw commerce data to a decision you can defend.</h2>
            </div>

            <div className="ex-flow">
              <div className="ex-step">
                <div className="ex-step-index">01</div>
                <strong>Find</strong>
                <p>
                  Identify the business decisions with the highest expected
                  economic relevance.
                </p>
              </div>

              <div className="ex-step">
                <div className="ex-step-index">02</div>
                <strong>Compare</strong>
                <p>
                  Generate feasible alternatives and compare them with
                  business-as-usual.
                </p>
              </div>

              <div className="ex-step">
                <div className="ex-step-index">03</div>
                <strong>Estimate</strong>
                <p>
                  Model expected contribution profit, uncertainty, and credible
                  downside.
                </p>
              </div>

              <div className="ex-step">
                <div className="ex-step-index">04</div>
                <strong>Decide</strong>
                <p>
                  Recommend ACT, TEST, BAU, or AVOID based on the evidence
                  available.
                </p>
              </div>

              <div className="ex-step">
                <div className="ex-step-index">05</div>
                <strong>Learn</strong>
                <p>
                  Compare outcomes with expectations and improve the next
                  decision.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="ex-trust" id="research">
          <div className="ex-wrap ex-trust-grid">
            <div>
              <div className="ex-section-num" style={{ marginBottom: 22 }}>
                02 · Built for trust
              </div>
              <h2>A recommendation is not an order.</h2>
              <p className="ex-trust-copy">
                Exergi is designed for decisions that affect real economics.
                Recommendations show the evidence, uncertainty, and
                business-as-usual baseline behind them. The business remains in
                control.
              </p>
            </div>

            <div className="ex-trust-list">
              <div className="ex-trust-row">
                <span>Control</span>
                <strong>
                  Read-only by default. No autonomous store changes.
                </strong>
              </div>
              <div className="ex-trust-row">
                <span>Evidence</span>
                <strong>
                  Every recommendation shows why Exergi believes it beats BAU.
                </strong>
              </div>
              <div className="ex-trust-row">
                <span>Uncertainty</span>
                <strong>
                  Confidence and downside are shown explicitly instead of hidden
                  behind a score.
                </strong>
              </div>
              <div className="ex-trust-row">
                <span>Human</span>
                <strong>
                  You decide what to implement, test, or leave unchanged.
                </strong>
              </div>
            </div>
          </div>
        </section>

        <section className="ex-final" id="partners">
          <div className="ex-wrap">
            <div className="ex-final-box">
              <div>
                <div className="ex-section-num" style={{ marginBottom: 20 }}>
                  Design partners
                </div>
                <h2>Help shape the decision layer for commerce.</h2>
                <p>
                  Join a small group of operators testing Exergi on real
                  commerce data and helping define what decision intelligence
                  should become.
                </p>
              </div>

              <a className="ex-primary" href="mailto:hello@exergi.co">
                Join design partners <span className="ex-arrow">→</span>
              </a>
            </div>

            <footer className="ex-site-footer">
              <span>© 2026 Exergi</span>
              <div className="ex-site-footer-links">
                <a href="#">Privacy</a>
                <a href="#">Terms</a>
                <a href="#">Contact</a>
              </div>
            </footer>
          </div>
        </section>
      </main>
    </>
  );
}
