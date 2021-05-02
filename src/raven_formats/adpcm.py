steps = [
    7, 8, 9, 10, 11, 12, 13, 14,
    16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66,
    73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484,
    7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767
]

step_indices = [-1, -1, -1, -1, 2, 4, 6, 8]

def clamp(value, lower, upper):
    return lower if (value < lower) else upper if (value > upper) else value

def decode_sample(sample: int, state: tuple) -> tuple:
    predicted_sample = state[0]
    step_index = state[1]
    step = steps[step_index]

    diff = step >> 3
    if sample & 1: diff += step >> 2
    if sample & 2: diff += step >> 1
    if sample & 4: diff += step
    if sample & 8: diff = -diff
    
    predicted_sample = clamp(predicted_sample + diff, -32768, 32767)
    step_index = clamp(step_index + step_indices[sample & 7], 0, 88)

    return predicted_sample, step_index

def encode_sample(sample: int, state: tuple) -> tuple:
    predicted_sample = state[0]
    step_index = state[1]
    step = steps[step_index]

    sample_diff = sample - predicted_sample
    encoded_sample = 0

    if sample_diff < 0:
        sample_diff = -sample_diff
        encoded_sample = 8
    
    diff = step >> 3
    if sample_diff >= step:
        encoded_sample |= 4
        sample_diff -= step
        diff += step

    step >>= 1
    if sample_diff >= step:
        encoded_sample |= 2
        sample_diff -= step
        diff += step

    step >>= 1
    if sample_diff >= step:
        encoded_sample |= 1
        diff += step

    if encoded_sample & 8:
        diff = -diff
    
    predicted_sample = clamp(predicted_sample + diff, -32768, 32767)
    step_index = clamp(step_index + step_indices[encoded_sample & 7], 0, 88)

    return encoded_sample, (predicted_sample, step_index)

import wave, struct, time

def decode(samples: bytes) -> bytearray:
    samples = memoryview(samples).cast('B')
    decoded_samples = bytearray()
    state = (0, 0)

    for sample in samples:
        state = decode_sample(sample & 0xF, state)
        decoded_samples += struct.pack('<h', state[0])
        state = decode_sample((sample >> 4) & 0xF, state)
        decoded_samples += struct.pack('<h', state[0])
    return decoded_samples

def encode(samples: bytes) -> bytearray:
    samples = memoryview(samples).cast('h')
    encoded_samples = bytearray()
    state = (0, 0)
    low_sample = 0
    high_sample = False

    for sample in samples:
        sample, state = encode_sample(sample, state)

        if high_sample:
            encoded_samples.append(sample << 4 | low_sample)
        else:
            low_sample = sample

        high_sample = not high_sample
    return encoded_samples