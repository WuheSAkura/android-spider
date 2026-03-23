import { formatStatus } from "@/lib/api";

type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps): React.JSX.Element {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" />
      {formatStatus(status)}
    </span>
  );
}
