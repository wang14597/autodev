import hljs from 'highlight.js/lib/common'
import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'

/**
 * 剥掉模型给整份输出套的 ```markdown / ```md 外壳。
 *
 * 上下文简报常出现「导语 + ```markdown\n<整份文档>\n```」的结构——外壳让整段被当成
 * 代码块渲染成大片等宽灰块。这里把 markdown/md 信息串的围栏替换为其内部内容,使其按真正
 * 的 Markdown 排版。真实代码围栏(```bash/```python 等)不受影响。
 */
export function unwrapMarkdownFence(md: string): string {
  return md.replace(/```(?:markdown|md)[^\n]*\n([\s\S]*?)```/g, (_m, inner: string) => inner)
}

const marked = new Marked(
  markedHighlight({
    emptyLangClass: 'hljs',
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
      return hljs.highlight(code, { language }).value
    },
  }),
)

/** 解包外壳 → 解析为 HTML(GFM + 代码高亮)。调用方须再经 DOMPurify 消毒。 */
export function renderMarkdown(md: string): string {
  return marked.parse(unwrapMarkdownFence(md), { async: false }) as string
}
