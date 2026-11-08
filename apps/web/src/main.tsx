import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConsoleShell } from "@/components/console/ConsoleShell";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html is missing the #root element");

createRoot(root).render(
  <StrictMode>
    <ConsoleShell />
  </StrictMode>,
);
