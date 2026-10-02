import { Link } from "react-router-dom";
export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <li key={`${item.label}:${index}`} className="flex min-w-0 items-center gap-1">
              {index > 0 ? <span aria-hidden="true">/</span> : null}
              {item.to && !isLast ? (
                <Link to={item.to} className="truncate hover:text-foreground">{item.label}</Link>
              ) : (
                <span
                  className="truncate"
                  aria-current={isLast ? "page" : undefined}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}