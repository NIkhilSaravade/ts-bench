import raw from '../../data/results.json'
import type { Results } from './types'

/** The real results, exported from the raw run files. Nothing on the page is typed in by hand. */
export const data = raw as unknown as Results
