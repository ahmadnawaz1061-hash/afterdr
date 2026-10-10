export default function Card({
  as: Element = 'section',
  title,
  titleId,
  icon: Icon,
  status,
  children,
  footer,
  className = '',
  ...props
}) {
  return (
    <Element
      className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-5 ${className}`}
      aria-labelledby={titleId}
      {...props}
    >
      {(title || Icon || status) && (
        <header className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            {Icon && (
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-800">
                <Icon size={20} aria-hidden="true" />
              </span>
            )}
            {title && <h2 id={titleId} className="pt-1.5 text-base font-bold text-slate-950">{title}</h2>}
          </div>
          {status && <div className="shrink-0">{status}</div>}
        </header>
      )}
      <div className={(title || Icon || status) ? 'mt-4' : ''}>{children}</div>
      {footer && <footer className="mt-5 border-t border-slate-100 pt-4">{footer}</footer>}
    </Element>
  );
}
