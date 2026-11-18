// A four-step guided tour for first-time visitors: what each screen shows, in one or two sentences,
// with a Next button. It follows one story (a boiler the plan thinks was never replaced) from the board
// to the evidence to the results. Hidden with "Hide the guide", remembered in this browser.
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Icon } from "./Icons";

const BOILER = `/queue/${encodeURIComponent("W:overdue:A10-BOIL-A:2020")}`;

const STEPS = [
  {
    path: "/",
    title: "This is the board view",
    text: "Each card is one homeowners association. Red means something in its spending doesn't match its reserve plan. Start with Cobbs Creek.",
    next: "/associations/A10",
    nextLabel: "Open Cobbs Creek",
  },
  {
    path: "/associations/A10",
    title: "One association, plan against actual",
    text: "Grey bars are what the reserve plan expected to spend each year; blue is what was actually spent. Both boilers were due in 2020, but only one replacement shows up.",
    next: BOILER,
    nextLabel: "See the boiler warning",
  },
  {
    path: BOILER,
    title: "A warning, and the evidence",
    text: "The app says the Bldg A boiler was never replaced. The highlighted invoices suggest it was: they were filed under the Bldg B boiler. A manager fixes that in one click, and both warnings clear.",
    next: "/results",
    nextLabel: "How well does it work?",
  },
  {
    path: "/results",
    title: "How well it works",
    text: "Four numbers that sum it up. The full tables and the caveats are one click away at the bottom.",
    next: "/",
    nextLabel: "Back to the board",
  },
] as const;

const KEY = "capital-drift.tour-hidden";

function readHidden(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function Tour() {
  const location = useLocation();
  const [hidden, setHidden] = useState(readHidden);
  const at = STEPS.findIndex((s) => s.path === location.pathname);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, hidden ? "1" : "0");
    } catch {
      /* storage unavailable: keep the in-memory choice */
    }
  }, [hidden]);

  if (hidden) {
    return (
      <button className="tour-reopen quiet-button" onClick={() => setHidden(false)}>
        <Icon name="help" size={16} /> Show the guide
      </button>
    );
  }
  if (at < 0) {
    return (
      <div className="tour tour-off" role="note">
        <span>New here? Take the four-step tour.</span>
        <Link className="button" to="/">
          Start the tour
        </Link>
        <button className="quiet-button" onClick={() => setHidden(true)}>
          Hide
        </button>
      </div>
    );
  }
  const step = STEPS[at];
  return (
    <div className="tour" role="note" aria-label="Guided tour">
      <span className="tour-count">
        {at + 1} of {STEPS.length}
      </span>
      <div className="tour-text">
        <strong>{step.title}.</strong> {step.text}
      </div>
      <div className="tour-actions">
        <Link className="button primary" to={step.next}>
          {step.nextLabel} <Icon name="arrowRight" size={16} />
        </Link>
        <button className="quiet-button" onClick={() => setHidden(true)}>
          Hide the guide
        </button>
      </div>
    </div>
  );
}
