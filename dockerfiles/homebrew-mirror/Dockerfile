FROM alpine:3.11

RUN apk add --no-cache bash git curl ncurses ruby ruby-bigdecimal ruby-fiddle ruby-json ruby-etc ruby-irb ruby-json ruby-test-unit

RUN git clone --depth 1 https://github.com/Homebrew/brew.git /home/homebrew/.linuxbrew/homebrew && cd /home/homebrew/.linuxbrew && mkdir bin && ln -s /home/homebrew/.linuxbrew/homebrew/bin/brew /home/homebrew/.linuxbrew/bin

RUN git clone --depth 1 https://github.com/gaoyifan/homebrew-bottle-mirror.git /home/homebrew/.linuxbrew/homebrew/Library/Taps/gaoyifan/homebrew-bottle-mirror

RUN chown -R 2000 /home/homebrew
