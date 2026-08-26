import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { AppHeader } from "./AppHeader";
import { SideNav } from "./SideNav";
import { GuidedTour } from "./GuidedTour";
import { ToastHost } from "../ui";
import { useData } from "../../data/store";

export function Layout() {
  const { load, loaded } = useData();
  useEffect(() => {
    load();
  }, [load]);

  if (!loaded) {
    return (
      <div className="loader">
        <div className="l-brand">
          <img src={`${import.meta.env.BASE_URL}brand/optum_financial_logo.svg`} alt="Optum Financial" />
        </div>
        <div className="spinner" />
        <div className="muted small">Loading provider master data…</div>
      </div>
    );
  }

  return (
    <div className="app">
      <AppHeader />
      <div className="appbody">
        <SideNav />
        <main className="appmain">
          <Outlet />
        </main>
      </div>
      <GuidedTour />
      <ToastHost />
    </div>
  );
}
