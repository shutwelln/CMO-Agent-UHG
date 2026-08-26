import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { X, ArrowRight, ArrowLeft, Sparkles } from "lucide-react";
import { useTour, TOUR_STEPS } from "../../context/tour";
import { useRole } from "../../context/role";

export function GuidedTour() {
  const { active, step, next, prev, stop } = useTour();
  const setRole = useRole((s) => s.setRole);
  const navigate = useNavigate();

  const current = TOUR_STEPS[step];

  // Drive the app: on each step set the role and navigate to the screen.
  useEffect(() => {
    if (!active || !current) return;
    setRole(current.role);
    navigate(current.path);
  }, [active, step, current, setRole, navigate]);

  if (!active || !current) return null;

  return (
    <div className="tour-card" role="dialog" aria-label="Guided tour">
      <div className="tour-hd">
        <span className="tour-badge">
          <Sparkles size={13} /> Guided tour
        </span>
        <span className="tour-count">
          {step + 1} / {TOUR_STEPS.length}
        </span>
        <button className="tour-x" onClick={stop} aria-label="End tour">
          <X size={16} />
        </button>
      </div>
      <div className="tour-title">{current.title}</div>
      <div className="tour-body">{current.body}</div>
      <div className="tour-ft">
        <button className="btn btn-text" onClick={stop}>
          End tour
        </button>
        <div className="row gap-2">
          {step > 0 && (
            <button className="btn btn-outline btn-sm" onClick={prev}>
              <ArrowLeft size={15} /> Back
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={next}>
            {step >= TOUR_STEPS.length - 1 ? "Finish" : "Next"} <ArrowRight size={15} />
          </button>
        </div>
      </div>
      <div className="tour-progress">
        <span style={{ width: `${((step + 1) / TOUR_STEPS.length) * 100}%` }} />
      </div>
    </div>
  );
}
