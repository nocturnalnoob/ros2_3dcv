import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { CourseMap } from "./components/CourseMap";
import { Workbench } from "./components/Workbench";
import { useApplyTheme } from "./components/ThemeToggle";
import "./styles.css";

const qc = new QueryClient();

function App() {
  useApplyTheme(); // sync persisted theme -> <html data-theme>
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CourseMap />} />
        <Route path="/module/:id" element={<Workbench />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
