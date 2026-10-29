"""Chat-selected, bounded reasoning effort. No backend or settings UI ownership."""
LEVELS = ('low','medium','high','extra_high')
REASONING_TOKENS = {'low':256,'medium':1024,'high':2048,'extra_high':4096}
OUTPUT_TOKENS = {'low':2048,'medium':4096,'high':6144,'extra_high':8192}


def normalize_thinking_level(value):
    value=str(value or '').strip().casefold().replace(' ','_').replace('-','_')
    return value if value in LEVELS else 'low'


def reasoning_tokens(level, output_limit):
    return min(REASONING_TOKENS[normalize_thinking_level(level)],max(1,int(output_limit)-1024))


def output_tokens(level, routed_limit, context_limit):
    return max(32,min(int(context_limit)-768,max(int(routed_limit),OUTPUT_TOKENS[normalize_thinking_level(level)])))
