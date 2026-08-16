import './GroupedCategoryOptions.css'

interface Props {
  groups: Array<{
    group: { id: string; name: string }
    cats: Array<{ id: string; name: string }>
  }>
}

/* Native select popups on macOS ignore option CSS entirely, so the hierarchy
 * has to live in the text: category options are indented (non-breaking
 * spaces — regular ones collapse) under their group label. Browsers that do
 * style popups additionally get the CSS treatment. */
const INDENT = '   '

export function GroupedCategoryOptions({ groups }: Props) {
  return (
    <>
      {groups.map(({ group, cats }) => (
        <optgroup key={group.id} label={group.name} className="grouped-cat__group">
          {cats.map((c) => (
            <option key={c.id} value={c.id} className="grouped-cat__option">
              {INDENT}
              {c.name}
            </option>
          ))}
        </optgroup>
      ))}
    </>
  )
}
