// src/features/prompt-studio/components/SyntaxHighlighter.jsx
// Placeholder for SyntaxHighlighter — implement component/logic here.

// src/features/prompt-studio/components/SyntaxHighlighter.jsx

const VARIABLE_SPLIT = /(\{\{[a-zA-Z0-9_]+\}\})/g;
const VARIABLE_MATCH = /^\{\{[a-zA-Z0-9_]+\}\}$/;

function tokenize(line) {
  return line
    .split(VARIABLE_SPLIT)
    .filter(Boolean)
    .map((part) => ({ text: part, isVariable: VARIABLE_MATCH.test(part) }));
}

/**
 * Renders a single line of a master prompt with lightweight syntax coloring:
 * - "### " section headers -> green
 * - numbered list items ("1. ") -> orange
 * - {{template_variables}} -> cyan, regardless of line type
 */
export default function SyntaxHighlighter({ line }) {
  if (line.trim() === "") return <span>&nbsp;</span>;

  const isHeader = /^###\s/.test(line);
  const isNumbered = /^\d+\.\s/.test(line);
  const tokens = tokenize(line);

  if (isHeader) {
    return <span className="text-emerald-400 font-semibold">{line}</span>;
  }

  return (
    <span className={isNumbered ? "text-orange-300" : "text-slate-200"}>
      {tokens.map((token, i) =>
        token.isVariable ? (
          <span key={i} className="text-cyan-300">
            {token.text}
          </span>
        ) : (
          <span key={i}>{token.text}</span>
        ),
      )}
    </span>
  );
}
