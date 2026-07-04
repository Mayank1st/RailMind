def city_image_prompt(city_name: str) -> str:
    """Weekly homepage carousel card image for one trending destination city.
    Subject stays centered — card edges get cropped at different breakpoints."""
    return (
        f"A stunning, vibrant travel-photography style image of {city_name}, India, "
        f"that makes people want to book a train trip there. Blend the city's most "
        f"iconic tourism landmark or scenery with Indian Railways: a modern Indian "
        f"train, railway station architecture or tracks elegantly integrated into "
        f"the scene. Golden-hour light, rich colors, inviting atmosphere. "
        f"Composition rules: main subject perfectly centered in the frame, wide "
        f"landscape framing with safe margins on the left and right edges, no text, "
        f"no watermarks, no logos, photorealistic."
    )
