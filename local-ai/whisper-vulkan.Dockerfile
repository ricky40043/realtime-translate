# whisper.cpp 語音辨識伺服器（Vulkan：Intel / AMD 內顯也能加速），給家裡伺服器用。
# 官方映像檔 v1.9.5 在 Intel Core Ultra 上會 illegal instruction（用了這顆 CPU 沒有的指令），
# v1.9.4 卡在啟動，所以自己從 v1.9.5 原始碼編譯，GGML_NATIVE=OFF 讓任何 x86 CPU 都能跑。
FROM ubuntu:24.04 AS build
RUN apt-get update && apt-get install --no-install-recommends -y \
      build-essential ca-certificates cmake git glslc libvulkan-dev spirv-headers \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.9.5 https://github.com/ggml-org/whisper.cpp /src
WORKDIR /src
RUN cmake -B build -DGGML_VULKAN=1 -DGGML_NATIVE=OFF -DWHISPER_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j --target whisper-server \
    && mkdir -p /out/bin /out/lib \
    && cp build/bin/whisper-server /out/bin/ \
    && find build -name "*.so*" -exec cp -a {} /out/lib/ \;

FROM ubuntu:24.04
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates libvulkan1 mesa-vulkan-drivers libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/bin/ /usr/local/bin/
COPY --from=build /out/lib/ /usr/local/lib/
RUN ldconfig
EXPOSE 8080
CMD ["whisper-server", "--help"]
