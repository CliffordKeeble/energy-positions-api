import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Testing Library only tidies up after each test by itself when the test runner has
// global hooks; this suite imports its own, so it is done here.
afterEach(cleanup)
