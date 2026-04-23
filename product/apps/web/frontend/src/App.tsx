import { Route, Routes, Navigate } from "react-router-dom";
import AppHeader from "./components/AppHeader";
import StepIndicator from "./components/StepIndicator";
import SebiModal from "./components/SebiModal";
import Step1Tier from "./routes/Step1Tier";
import Step2Profile from "./routes/Step2Profile";
import Step3Strategy from "./routes/Step3Strategy";
import Step4Plan from "./routes/Step4Plan";
import VerifyMagic from "./routes/VerifyMagic";

export default function App() {
  return (
    <div className="min-h-full flex flex-col">
      <AppHeader />
      <SebiModal />
      <StepIndicator />
      <main className="max-w-4xl w-full mx-auto px-4 py-8 flex-1">
        <Routes>
          <Route path="/" element={<Navigate to="/step/1" replace />} />
          <Route path="/step/1" element={<Step1Tier />} />
          <Route path="/step/2" element={<Step2Profile />} />
          <Route path="/step/3" element={<Step3Strategy />} />
          <Route path="/step/4" element={<Step4Plan />} />
          <Route path="/verify" element={<VerifyMagic />} />
          <Route path="*" element={<Navigate to="/step/1" replace />} />
        </Routes>
      </main>
      <footer className="border-t border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-4">
        <p className="text-xs text-gray-500 dark:text-slate-400 text-center">
          Benji — part of the <span className="font-medium">Subprime</span> research project
        </p>
      </footer>
    </div>
  );
}
