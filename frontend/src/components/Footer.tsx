import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer className="border-t border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Main Footer Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8">
          {/* Brand Column */}
          <div className="lg:col-span-2">
            <div className="flex items-center gap-2 font-bold text-xl text-gray-900 dark:text-white mb-4">
              <img src="/logo.png" className='w-8 h-8 object-cover' alt="Sunbird AI" />
              <span>Sunbird AI</span>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 max-w-sm">
              Empowering African languages with state-of-the-art AI models for translation, transcription, and speech synthesis.
            </p>
            {/* Social Media Links */}
            <div className="flex gap-2">
              <a 
                href="https://twitter.com/sunbirdai" 
                target="_blank" 
                rel="noopener noreferrer"
                // className='p-2'
                aria-label="Twitter"
              >
                {/* <Twitter size={20} /> */}
                <svg className="w-5 h-5 bg-gray-400 dark:bg-gray-500 hover:bg-gray-500 dark:hover:bg-gray-400" style={{
                  WebkitMaskImage: "url(https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/brands/x-twitter.svg)",
                  WebkitMaskRepeat: "no-repeat",
                  WebkitMaskPosition: "center",
                  maskImage: "url(https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/brands/x-twitter.svg)",
                  maskRepeat: "no-repeat",
                  maskPosition: "center"
                }}></svg>
              </a>
              <a 
                href="https://github.com/SunbirdAI" 
                target="_blank" 
                rel="noopener noreferrer"
                // className="p-2"
                aria-label="GitHub"
              >
                {/* <Github size={20} /> */}
                <svg className="w-5 h-5 bg-gray-400 dark:bg-gray-500 hover:bg-gray-500 dark:hover:bg-gray-400" style={{
                  WebkitMaskImage: "url(https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/brands/github.svg)",
                  WebkitMaskRepeat: "no-repeat",
                  WebkitMaskPosition: "center",
                  maskImage: "url(https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/brands/github.svg)",
                  maskRepeat: "no-repeat",
                  maskPosition: "center"
                }}></svg>
              </a>
              <a 
                href="https://www.linkedin.com/company/sunbird-ai" 
                target="_blank" 
                rel="noopener noreferrer"
                // className="p-2"
                aria-label="LinkedIn"
              >
                {/* <Linkedin size={20} /> */}
               <svg className="w-5 h-5 bg-gray-400 dark:bg-gray-500 hover:bg-gray-500 dark:hover:bg-gray-400" style={{
                  WebkitMaskImage: "url(https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/brands/linkedin.svg)",
                  WebkitMaskRepeat: "no-repeat",
                  WebkitMaskPosition: "center",
                  maskImage: "url(https://d3gk2c5xim1je2.cloudfront.net/v7.1.0/brands/linkedin.svg)",
                  maskRepeat: "no-repeat",
                  maskPosition: "center"
                }}></svg>    </a>
              {/* <a 
                href="mailto:info@sunbird.ai"
                className="p-2 rounded-full bg-gray-200 dark:bg-white/10 hover:bg-primary-500 dark:hover:bg-primary-500 text-gray-700 dark:text-gray-300 hover:text-white transition-colors"
                aria-label="Email"
              >
                <Mail size={20} />
              </a> */}
            </div>
          </div>

          {/* Resources Column */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Resources</h3>
            <ul className="space-y-3">
              <li>
                <a href="https://docs.sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Documentation
                </a>
              </li>
              <li>
                <a href="https://github.com/SunbirdAI/sunbird-ai-api" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  API Reference
                </a>
              </li>
              <li>
                <a href="https://github.com/SunbirdAI/translation-api-examples" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Code Examples
                </a>
              </li>
              <li>
                <a href="https://github.com/SunbirdAI/sunbird-ai-api/blob/main/tutorial.md" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Tutorial
                </a>
              </li>
            </ul>
          </div>

          {/* Products Column */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Products</h3>
            <ul className="space-y-3">
              <li>
                <a href="https://sunflower.sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Sunflower
                </a>
              </li>
              <li>
                <Link to="https://sunflower.sunbird.ai" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Translation
                </Link>
              </li>
              <li>
                <Link to="https://speech.sunbird.ai" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Speech
                </Link>
              </li>
            </ul>
          </div>

          {/* Company Column */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Company</h3>
            <ul className="space-y-3">
              <li>
                <a href="https://sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  About Us
                </a>
              </li>
              <li>
                <a href="https://blog.sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Blog
                </a>
              </li>
              <li>
                <Link to="/privacy_policy" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link to="/terms_of_service" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>
        </div>

        
      </div>
      {/* Bottom Bar */}
        <div className="py-5 border-t border-gray-200 dark:border-white/10 flex items-center justify-center">       
            <p className="text-sm text-gray-500 dark:text-gray-400">
              &copy; {new Date().getFullYear()} Sunbird AI. All rights reserved.
        </p>
        
        </div>
    </footer>
  );
}
