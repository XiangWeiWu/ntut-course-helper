import { useState } from "react";
import Student from "./pages/Student";
import Teacher from "./pages/Teacher";
import Sim from "./pages/Sim";
import Optimize from "./pages/Optimize";

const TABS = { optimize: "系所排課最佳化", student: "學生：查課與排課", teacher: "教授／系所：需求預測", sim: "選課模擬" } as const;
type Tab = keyof typeof TABS;

export default function App() {
  const [tab, setTab] = useState<Tab>("optimize");
  return (
    <>
      <header>
        <h1>北科選課助手（雛形）</h1>
        <nav>{(Object.keys(TABS) as Tab[]).map((k) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{TABS[k]}</button>)}</nav>
        <span className="muted" style={{ marginLeft: "auto" }}>115-1 課程資料：北科課程好朋友（gnehs/ntut-course-crawler-node）· 非官方系統</span>
      </header>
      <main>{tab === "optimize" ? <Optimize /> : tab === "student" ? <Student /> : tab === "teacher" ? <Teacher /> : <Sim />}</main>
    </>
  );
}
